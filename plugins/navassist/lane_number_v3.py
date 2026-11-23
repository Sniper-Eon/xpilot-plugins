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


class LaneNumberV3:
    def __init__(self, cfg: V3Config | None = None):
        self.cfg = cfg or V3Config()
        self.reset()

    # ------------------------------------------------------------------ state
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

    # -------------------------------------------------------------- helpers
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

    # ---------------------------------------------------------------- update
    def update(self, f: dict) -> dict:
        c = self.cfg
        t = float(f["t"])
        dt = 0.0 if self.t_prev is None else max(0.0, min(1.0, t - self.t_prev))
        self.t_prev = t
        n_in = self._n_now(f)
        dist = f.get("dist_m")
        near = isinstance(dist, (int, float)) and 0.0 < dist <= c.junction_m
        w = self._width(f)
        off = f.get("gps_off_m")
        if off is not None and abs(off) <= 25:
            self.offs.append(off)

        # ---- step tracking: drop the lock after passing a turning manoeuvre
        man = str(f.get("maneuver") or "none")
        key = (man, f.get("event_id") or "")
        new_step = False
        if self.step_key is None:
            self.step_key, self.step_man, self.step_min_d = key, man, dist
        else:
            jumped = (isinstance(dist, (int, float)) and isinstance(self.step_min_d, (int, float))
                      and dist - self.step_min_d >= 80 and dist >= 40)
            if key != self.step_key or jumped:
                new_step = True
                passed_close = isinstance(self.step_min_d, (int, float)) and self.step_min_d <= c.junction_m
                if (c.unlock_after_turn and passed_close and self.step_man.startswith(TURNING)
                        and self.value is not None):
                    self._set(None, "UNLOCKED", "afterTurn:" + self.step_man, t, n_in)
                    self.last_shown = None
                self.step_key, self.step_man, self.step_min_d = key, man, dist
            elif isinstance(dist, (int, float)):
                self.step_min_d = dist if self.step_min_d is None else min(self.step_min_d, dist)

        # ---- current layout latch + future-layout snapshot
        # The planning distance gate says when a manoeuvre may be prepared.  It
        # does NOT prove that the car has entered the widened junction layout.
        # Keep AMap's count as a pending future snapshot and number the car only
        # in the independently latched current-road coordinate system.
        approaching = in_approach_window(dist, f.get("road_kind"), man)
        amap_n = int(f.get("n_amap") or 0)
        if self.n is not None and amap_n >= 1 and amap_n != self.n:
            if self.pending_n != amap_n:
                self.pending_n, self.pending_t0 = amap_n, t
        else:
            self.pending_n, self.pending_t0 = None, None

        n = self.n if self.n is not None else n_in
        if self.n is None and n_in is not None:
            self.n = n = n_in
        elif self.n is not None and n_in is not None and n_in != self.n:
            # A current-layout source reports a new total, but it still does not
            # say how old lanes connect to new lanes.  Per driver preference,
            # retain the OLD-road number and mark it pending; do not reinterpret
            # the same integer in the new coordinate system and do not guess an
            # added-left offset.
            self.pending_current_n = n_in
            self.pending_n = n_in
            self.state = "TENTATIVE" if self.value is not None else "UNLOCKED"
            self.reason = "layoutPending:%d->%d" % (self.n, n_in)
            n = self.n
        elif n_in == self.n:
            self.pending_current_n = None
        if f.get("rec") and amap_n == self.n:
            self.rec_prev = tuple(f.get("rec"))

        if n is None:
            if self.value is not None:
                self._set(None, "UNLOCKED", "noLaneCount", t, None)
            return self._out(f, None, None)

        # ---- sources
        fz = f.get("fused_value")
        fz_ok = (not f.get("fused_err")) and isinstance(fz, int) and 0 <= fz < n and (f.get("fused_conf") or 0) >= c.fused_min
        fz_strong = fz_ok and (f.get("fused_conf") or 0) >= c.fused_strong
        cam, mnn, pair, vis_single = self._vision(f, n)
        if pair is not None:
            if self.pair_v != pair:
                self.pair_v, self.pair_t0 = pair, t
        else:
            self.pair_v, self.pair_t0 = None, None
        pair_stable = self.pair_v is not None and t - self.pair_t0 >= c.vision_pair_min_s

        # ---- lane-change state machine (car)
        # This C3 fork does not emit laneChangeFinishing.  Starting ending only
        # means the model's lane-change probability fell; it may be completion
        # OR cancellation.  Hold the old number and wait for the fused/visual
        # lane estimate to remain on the expected adjacent lane.
        lcs = str(f.get("lcs") or "")
        lcs_low = lcs.lower()
        starting = "starting" in lcs_low
        lc_event = None
        if starting:
            if self.lc_t0 is None:
                self.lc_t0 = t
                hacc = f.get("gps_hacc_m")
                self.lc_start_gps = (f.get("gps_off_m")
                                     if hacc is not None and hacc <= c.gps_shift_max_hacc_m else None)
                self.lc_start_dr = f.get("lc_dr_lat")
            d = f.get("lc_dir")
            if d in ("left", "right"):
                self.lc_dir = d
        elif self.lc_t0 is not None:
            if (t - self.lc_t0 >= c.lc_min_starting_s and self.lc_dir
                    and self.value is not None and n >= 1):
                step = -1 if self.lc_dir == "left" else 1
                target = max(0, min(n - 1, self.value + step))
                if target != self.value:
                    self.lc_pending = {"direction": self.lc_dir, "target": target,
                                       "t0": t, "support_t0": None,
                                       "gps0": self.lc_start_gps, "dr0": self.lc_start_dr}
            self.lc_t0, self.lc_dir = None, None
            self.lc_start_gps, self.lc_start_dr = None, None

        if self.lc_pending is not None and not starting:
            p = self.lc_pending
            fused_supported = bool(fz_strong and fz == p["target"])
            vision_supported = bool(pair_stable and self.pair_v == p["target"])
            sign = -1 if p["direction"] == "left" else 1
            need_motion = c.lc_shift_frac * w
            dr_now, gps_now = f.get("lc_dr_lat"), f.get("gps_off_m")
            dr_delta = (sign * (dr_now - p["dr0"])
                        if isinstance(dr_now, (int, float)) and isinstance(p["dr0"], (int, float)) else None)
            hacc = f.get("gps_hacc_m")
            gps_delta = (sign * (gps_now - p["gps0"])
                         if (isinstance(gps_now, (int, float)) and isinstance(p["gps0"], (int, float))
                             and hacc is not None and hacc <= c.gps_shift_max_hacc_m) else None)
            motion_confirmed = ((dr_delta is not None and dr_delta >= need_motion)
                                or (gps_delta is not None and gps_delta >= need_motion))
            # Completion is a 2-of-3 vote: physical lateral motion, fused lane,
            # and independent phone+camera visual pair.  This tolerates a
            # missing GPS source without allowing one drifting source to decide.
            evidence_count = int(motion_confirmed) + int(fused_supported) + int(vision_supported)
            if evidence_count >= 2:
                if p["support_t0"] is None:
                    p["support_t0"] = t
                elif t - p["support_t0"] >= c.lc_finish_confirm_s:
                    lc_event = p["direction"]
                    self.lc_pending = None
            else:
                p["support_t0"] = None
            if self.lc_pending is not None and t - p["t0"] >= c.lc_finish_timeout_s:
                self.lc_pending = None
        in_lc = starting
        self.lcs_prev = lcs
        if f.get("lc_dir") in ("left", "right"):
            self.blink_t, self.blink_dir = t, f.get("lc_dir")

        # ---- lateral shift (dead-reckoning first, GPS vs slow reference second)
        shift = None
        dr = f.get("dr_lat")
        if c.allow_inertial_lane_change and self.value is not None and not in_lc and lc_event is None:
            if isinstance(dr, (int, float)):
                if self.dr_ref is None:
                    self.dr_ref = dr
                if abs(dr - self.dr_ref) >= c.lc_shift_frac * w:
                    sdir = "right" if dr > self.dr_ref else "left"
                    sd = 1 if sdir == "right" else -1
                    target = max(0, min(n - 1, self.value + sd))
                    source_ok = ((fz_strong and fz == target)
                                 or (pair_stable and self.pair_v == target))
                    if (not c.inertial_requires_source) or source_ok:
                        shift = sdir
                    self.dr_ref = dr
            hacc = f.get("gps_hacc_m")
            if shift is None and len(self.offs) >= 3 and hacc is not None and hacc <= c.gps_shift_max_hacc_m:
                med = sorted(self.offs)[len(self.offs) // 2]
                if self.gps_ref is None:
                    self.gps_ref = med
                delta = med - self.gps_ref
                if abs(delta) >= c.lc_shift_frac * w:
                    sd = 1 if delta > 0 else -1
                    if self.shift_dir != sd:
                        self.shift_dir, self.shift_t0 = sd, t
                    elif t - self.shift_t0 >= c.lat_shift_sustain_s:
                        sdir = "right" if sd > 0 else "left"
                        target = max(0, min(n - 1, self.value + sd))
                        blink_ok = (self.blink_t is not None and t - self.blink_t <= c.blinker_memory_s
                                    and self.blink_dir == sdir)
                        src_ok = ((fz_strong and fz == target)
                                  or (pair_stable and self.pair_v == target))
                        if c.inertial_requires_source:
                            supported = src_ok and not near
                        else:
                            supported = (not c.shift_needs_support) or blink_ok or (src_ok and not near)
                        if supported:
                            shift = sdir
                        self.gps_ref = med
                        self.shift_dir = 0
                else:
                    self.shift_dir = 0
                    a = min(1.0, dt / c.gps_ref_tau_s) if c.gps_ref_tau_s > 0 else 1.0
                    self.gps_ref += a * (med - self.gps_ref)

        # ---- junction freeze bookkeeping
        if near and self.value is not None:
            if self.junction_t0 is None:
                self.junction_t0 = t
        elif not near:
            self.junction_t0 = None
        frozen = near and self.value is not None and (t - (self.junction_t0 or t)) <= c.hold_max_s

        # ================================================ state machine
        if self.value is not None:
            if in_lc:
                self.state, self.reason = "PAUSE", "laneChanging"
            elif lc_event or shift:
                d = lc_event or shift
                step = -1 if d == "left" else 1
                nv = max(0, min(n - 1, self.value + step))
                self.pre_lc_value = self.value
                self._set(nv, "TENTATIVE", ("lc_" if lc_event else "shift_") + d, t, n)
                self.tent_t0 = t
                self.dis_v = None
                if shift:
                    self.lc_pending = None
            else:
                if self.state == "PAUSE":
                    self.state = "TENTATIVE"     # LC ended without direction / aborted: reconfirm
                    self.tent_t0 = t
                # evidence that disagrees with the held number
                evid, corroborated = None, False
                if fz_strong and (vis_single is None or fz in vis_single):
                    evid = fz
                    corroborated = (vis_single is not None and fz in vis_single) or \
                        (self._gps_gate(f, n, self.value) is False and self._gps_gate(f, n, fz) is True)
                elif pair_stable and (not fz_ok or fz == self.pair_v):
                    if self.state != "LOCKED" or c.locked_visual_only_correction:
                        evid, corroborated = self.pair_v, True
                if (evid is not None and self.pre_lc_value is not None and evid == self.pre_lc_value
                        and not (pair_stable and self.pair_v == evid)
                        and t - (self.tent_t0 or t) <= c.lc_protect_s):
                    evid = None   # stale fused right after our own confirmed lane change
                gate = self._gps_gate(f, n, self.value)
                target_gate = self._gps_gate(f, n, evid) if evid is not None else None
                if frozen:
                    self.dis_v = None
                    self.gate_fail_t0 = None
                    if self.state in ("LOCKED", "TENTATIVE"):
                        self.reason = "junctionHold"
                else:
                    if evid is not None and evid != self.value and target_gate is not False:
                        if self.dis_v != evid:
                            self.dis_v, self.dis_t0 = evid, t
                        need = c.relock_s if corroborated else c.relock_fused_only_s
                        if self.state in ("TENTATIVE", "REMAP_UNSURE"):
                            need = need / 2.0
                        if t - self.dis_t0 >= need:
                            self._set(evid, "LOCKED", "corrected", t, n)
                            self.dis_v = None
                    else:
                        self.dis_v = None
                        if self.state in ("TENTATIVE", "REMAP_UNSURE"):
                            confirmed = (fz_ok and fz == self.value) or (pair_stable and self.pair_v == self.value)
                            if confirmed:
                                self.state, self.reason = "LOCKED", "reconfirmed"
                            elif t - (self.tent_t0 or t) > c.reconfirm_s and self.state == "REMAP_UNSURE":
                                self._set(None, "UNLOCKED", "remapNotConfirmed", t, n)
                            elif t - (self.tent_t0 or t) > c.reconfirm_s:
                                self.state, self.reason = "LOCKED", "noContradiction"
                    if self.value is not None:
                        if gate is False and c.gate_defer_to_fused and fz_strong and fz == self.value:
                            gate = None   # V3TUNE: strong fused agrees with the held number -> ignore GPS gate
                        if gate is False:
                            if self.gate_fail_t0 is None:
                                self.gate_fail_t0 = t
                            elif t - self.gate_fail_t0 >= c.gps_gate_fail_s:
                                self._set(None, "UNLOCKED", "gpsGate", t, n)
                                self.gate_fail_t0 = None
                        else:
                            self.gate_fail_t0 = None
        if self.value is None:
            # acquisition
            cand, why = None, ""
            if fz_ok:
                cand, why = fz, "fused"
                if vis_single is not None and fz not in vis_single and pair is not None:
                    cand, why = None, "visionConflict"
            elif pair is not None and c.vision_pair_can_lock:
                cand, why = pair, "visionPair"
            strong_cand = bool(cand is not None and why == "fused" and fz_strong)
            if cand is not None and self._gps_gate(f, n, cand) is False:
                if not (c.gate_defer_to_fused and strong_cand):
                    cand, why = None, "gpsGate"
            junction_ok = bool(near and c.junction_acquire_strong and strong_cand and cand is not None)
            if in_lc or (near and not junction_ok):
                # never start a new lock inside a lane change; inside the junction box only a strong,
                # long-stable fused value may start one (V3TUNE)
                cand = None
                why = "laneChanging" if in_lc else "inJunction"
            if cand is None:
                self.cand_v, self.cand_t0 = None, None
                self.state, self.reason = "UNLOCKED", why or "noCandidate"
            else:
                if self.cand_v != cand:
                    self.cand_v, self.cand_t0 = cand, t
                if near:
                    need = self._lock_s(f)                      # junction: full 3 s, strong fused only
                else:
                    need = self._lock_s(f, strong=strong_cand) + (1.0 if why == "visionPair" else 0.0)
                if t - self.cand_t0 >= need:
                    self._set(cand, "LOCKED", "lock:" + why, t, n)
                    self.gps_ref = None
                else:
                    self.state, self.reason = "UNLOCKED", "acquire:%s %.1fs" % (why, t - self.cand_t0)
        return self._out(f, n, pair if pair_stable else None)

    def _out(self, f, n, pair):
        c = self.cfg
        t = float(f["t"])
        strict = None
        provisional = False
        if self.value is not None and self.state in ("LOCKED", "TENTATIVE"):
            strict = self.value
        elif self.value is not None and self.state == "PAUSE" and not c.lc_strict_unknown:
            strict = self.value
        elif self.value is None and pair is not None:
            strict, provisional = pair, True
        hold = self.value
        if hold is None and self.last_shown is not None:
            v, n0, t0 = self.last_shown
            if t - t0 <= c.hold_stale_s and n is not None and n0 == n:
                hold = v
        if hold is None and pair is not None:
            hold = pair
        reason = self.reason
        if self.pending_current_n is not None and self.n is not None:
            reason = "layoutPending:%d->%d" % (self.n, self.pending_current_n)
        elif self.pending_n is not None and self.n is not None and self.pending_n != self.n:
            reason = "holdRoad:%d->%d" % (self.n, self.pending_n)
        return {"strict": strict, "hold": hold, "provisional": provisional, "state": self.state,
                "reason": reason, "n": n, "amap_rec": tuple(f.get("rec") or ()),
                "pending_n": self.pending_n, "approaching": in_approach_window(f.get("dist_m"), f.get("road_kind"), f.get("maneuver"))}

    def config_dict(self):
        return asdict(self.cfg)
