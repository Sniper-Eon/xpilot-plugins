"""lane_number_v3: lane-number arbiter that sits AFTER the fused filter.

Design (box prototype, not installed):
  * The fused filter (lane_fused / lanenav) stays the primary source.
  * A number is only shown after it has been stable for LOCK_S (3 s; 2 s urban test option)
    and is not contradicted by a vision pair (phone MNN + camera window) or by the GPS gate.
  * Once locked, the number is carried by an inertial tracker: it changes only on a confirmed
    lane change (laneChangeStarting -> done, direction from model/blinker) or on a lateral shift
    of >= 0.7 lane widths (dead-reckoning lateral if available, else GPS offset vs a slow reference).
  * From JUNCTION_M (80 m) before the manoeuvre through the junction the lock is frozen:
    no fused/vision corrections, only LC/lateral-shift and Amap count remaps.
  * Amap lane count must be stable COUNT_STABLE_S (0.8 s) before renumbering; a widening is
    remapped onto the side that did NOT widen (junction_side evidence, then recommended-set
    continuity); if neither is known the strict output goes to unknown until reconfirmed.
  * HOLD_ROAD: when Gaode's intersection (often widened) list appears early, the lock keeps
    the current-road numbering; remapping onto the intersection layout waits until the
    planning approach window (250 / 800 / 640 / 400 m). rec_prev is not updated while holding.
  * During a lane change the strict output is unknown ("变道中"), the hold output keeps the old
    number; afterwards the predicted number must be reconfirmed by the sources.
  * Fused error -> fused treated as absent, lock kept.
  * Unlocked: strict output is unknown; only when phone MNN and the camera window agree
    (both edge/class anchored) is a *provisional* number shown. NEVER falls back to the
    left/right-edge or phone-left estimators on their own.
  * GPS is a gate/correction only (1.8 lane widths), never the primary chooser.
  * Amap recommended lanes are passed through separately (amap_rec), never merged.

All lane numbers are 0-based from the left in the CURRENT numbering (Amap lane list when present,
otherwise the stable road total), like topology['absoluteEgoIndex'].

Pure Python, no openpilot imports. One instance per runtime; call update(frame) every tick.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field, asdict

from .rec_gate import in_approach_window

TURNING = ("turn_", "slight_", "ramp_", "uturn", "u_turn", "roundabout", "exit", "fork", "merge")


@dataclass
class V3Config:
    lock_s_highway: float = 3.0
    lock_s_urban: float = 3.0          # set 2.0 for the urban test option
    highway_kinds: tuple = ("expressway", "urban_expressway", "highway", "motorway")
    highway_speed_mps: float = 19.4    # 70 km/h fallback when road kind is unknown
    junction_m: float = 50.0           # V3TUNE 11-14: 80 -> 50 m (junction freeze distance)
    hold_max_s: float = 45.0
    count_stable_s: float = 0.8
    fused_min: float = 0.55
    fused_strong: float = 0.85
    gps_gate_lanes: float = 1.8
    gps_max_hacc_m: float = 10.0
    gps_gate_fail_s: float = 3.0
    gps_shift_max_hacc_m: float = 5.0
    lc_shift_frac: float = 0.7
    lat_shift_sustain_s: float = 1.5
    gps_ref_tau_s: float = 20.0
    lc_min_starting_s: float = 0.5
    lc_finish_confirm_s: float = 0.5  # target lane must stay supported after Starting ends
    lc_finish_timeout_s: float = 4.0  # otherwise the attempt is treated as cancelled
    reconfirm_s: float = 6.0
    relock_s: float = 4.0              # disagreement with corroboration (vision/GPS) before correcting
    relock_fused_only_s: float = 10.0  # fused alone must disagree this long before correcting
    shift_needs_support: bool = True   # GPS lateral shift needs blinker (last 10 s) or source support
    # Keep the existing inertial/visual correction behaviour.  The HOLD_ROAD
    # fix must not remove a useful correction path based on one drive alone.
    allow_inertial_lane_change: bool = True
    inertial_requires_source: bool = False
    locked_visual_only_correction: bool = True
    blinker_memory_s: float = 10.0
    lc_protect_s: float = 12.0         # after a confirmed LC, a fused value equal to the pre-LC lane is
                                       # treated as stale (fused gets no car LC events live) unless vision agrees
    vision_pair_min_s: float = 1.0
    vision_pair_can_lock: bool = True
    hold_stale_s: float = 60.0
    unlock_after_turn: bool = True
    lc_strict_unknown: bool = True
    width_default_m: float = 3.4
    # ---- V3TUNE 11-14 (road test 21:10-21:34: number shown only 71% of the time) ----
    lock_s_strong: float = 1.5         # fused >= fused_strong: lock after 1.5 s instead of 3 s
    junction_acquire_strong: bool = True   # inside junction_m: still allow a NEW lock from a strong fused
                                           # value that stayed stable for the full lock_s (3 s)
    gate_defer_to_fused: bool = True   # GPS gate failure is ignored when a strong fused value agrees
                                       # (fused already contains GPS; route line is not the road centre)


def _lane_centres(n, w):
    mid = (n - 1) / 2.0
    return [(k - mid) * w for k in range(n)]


def _jaccard_added_left(n_old, n_new, rec_old, rec_new):
    dlt = n_new - n_old
    cands = list(range(min(0, dlt), max(0, dlt) + 1))
    old, new = set(rec_old or ()), set(rec_new or ())
    if not old or not new or len(old) >= n_old or len(new) >= n_new:
        return None   # "all lanes recommended" carries no side information
    best, best_j = None, -1.0
    for a in cands:
        sh = {k + a for k in old if 0 <= k + a < n_new}
        u = sh | new
        j = len(sh & new) / len(u) if u else 0.0
        if j > best_j:
            best, best_j = a, j
    return best if best_j >= 0.5 else None


class LaneNumberState:
    def reset(self):
        self.state = "UNLOCKED"      # UNLOCKED, LOCKED, TENTATIVE, PAUSE, REMAP_UNSURE
        self.value = None
        self.n = None
        self.last_shown = None       # (value, n, t) for the hold output
        self.cand_v = None
        self.cand_t0 = None
        self.pair_v = None
        self.pair_t0 = None
        self.dis_v = None
        self.dis_t0 = None
        self.gate_fail_t0 = None
        self.n_raw = None
        self.n_raw_t0 = None
        self.pending_n = None   # Amap count held back until the approach window
        self.pending_t0 = None
        self.pending_current_n = None  # independently reported current-layout change, awaiting mapping
        self.rec_prev = ()
        self.offs = deque(maxlen=7)
        self.gps_ref = None
        self.shift_t0 = None
        self.shift_dir = 0
        self.lc_t0 = None
        self.lc_dir = None
        self.lc_start_gps = None
        self.lc_start_dr = None
        self.lc_pending = None       # dict(direction, target, t0, support_t0)
        self.lcs_prev = ""
        self.tent_t0 = None
        self.junction_t0 = None
        self.step_key = None
        self.step_man = None
        self.step_min_d = None
        self.t_prev = None
        self.reason = "init"
        self.dr_ref = None
        self.blink_t = None
        self.blink_dir = None
        self.pre_lc_value = None
    def _lock_s(self, f, strong=False):
        if strong and self.cfg.lock_s_strong > 0:
            return self.cfg.lock_s_strong
        kind = str(f.get("road_kind") or "")
        hw = kind in self.cfg.highway_kinds or (kind in ("", "unknown") and (f.get("speed") or 0) >= self.cfg.highway_speed_mps)
        return self.cfg.lock_s_highway if hw else self.cfg.lock_s_urban
    def _width(self, f):
        w = f.get("lane_width_m")
        return float(w) if isinstance(w, (int, float)) and 2.4 <= w <= 4.6 else self.cfg.width_default_m
    def _n_now(self, f):
        rt = f.get("road_total")
        # AMap's lane list describes the upcoming junction layout.  It is not a
        # current-road lane count and must never bootstrap the current numbering.
        amap_n = int(f.get("n_amap") or 0)
        if self.n is None and amap_n >= 1:
            return None
        return rt if isinstance(rt, int) and rt >= 1 else None
    def _vision(self, f, n):
        """Absolute candidates from phone MNN and from the camera window, each anchored."""
        cam, mnn = set(), set()
        if n:
            ego, vis = f.get("cam_ego"), f.get("cam_visible") or 0
            if isinstance(ego, int) and ego >= 0:
                if f.get("edge_l_anc"):
                    cam.add(ego)
                if f.get("edge_r_anc") and vis >= 1 and n - vis <= 1 and ego < vis:
                    cam.add(n - vis + ego)
            num, cnt = f.get("mnn_num"), f.get("mnn_cnt")
            if isinstance(num, int) and isinstance(cnt, int) and 1 <= num <= cnt:
                left_cls, right_cls = min(3, num), min(3, cnt - num + 1)
                if left_cls < 3:
                    mnn.add(num - 1)
                if right_cls < 3:
                    mnn.add(n - right_cls)
                if cnt == n:
                    mnn.add(num - 1)
        cam = {v for v in cam if 0 <= v < n} if n else set()
        mnn = {v for v in mnn if 0 <= v < n} if n else set()
        pair = None
        if len(cam) == 1 and len(mnn) == 1 and cam == mnn:
            pair = next(iter(cam))
        conflict_with = (cam | mnn) if (len(cam | mnn) == 1) else None
        return cam, mnn, pair, conflict_with
    def _added_left_now(self, f, n):
        rt = f.get("road_total")
        if not isinstance(rt, int) or rt < 1 or n is None or n == rt:
            return 0, True
        a = f.get("fused_side_added")
        dlt = n - rt
        if isinstance(a, int) and min(0, dlt) <= a <= max(0, dlt):
            return a, True
        return 0, False
    def _gps_gate(self, f, n, value):
        """True=consistent, False=inconsistent, None=no usable GPS."""
        off, hacc = f.get("gps_off_m"), f.get("gps_hacc_m")
        if off is None or n is None or value is None:
            return None
        if hacc is None or hacc > self.cfg.gps_max_hacc_m or abs(off) > 25:
            return None
        med = sorted(self.offs)[len(self.offs) // 2] if len(self.offs) >= 3 else off
        w = self._width(f)
        rt = f.get("road_total")
        # anchor on the road (non-widening) numbering
        a, _ = self._added_left_now(f, n)
        n_road = rt if isinstance(rt, int) and rt >= 1 else n
        v_road = value - a
        if not 0 <= v_road < n_road:
            v_road = max(0, min(n_road - 1, v_road))
        c = _lane_centres(n_road, w)[v_road]
        return abs(med - c) <= self.cfg.gps_gate_lanes * w
    def _remap(self, n_old, n_new, f):
        dlt = n_new - n_old
        a = f.get("fused_side_added")
        why = "side"
        if not (isinstance(a, int) and min(0, dlt) <= a <= max(0, dlt)):
            a = _jaccard_added_left(n_old, n_new, self.rec_prev, f.get("rec") or ())
            why = "rec"
        if a is None:
            return None, "unmapped"
        return max(0, min(n_new - 1, self.value + a)), why
    def _set(self, value, state, reason, t, n):
        if value != self.value:
            self.gps_ref = None
            self.dr_ref = None
        self.value, self.state, self.reason, self.n = value, state, reason, n
        if value is not None:
            self.last_shown = (value, n, t)
    def config_dict(self):
        return asdict(self.cfg)
