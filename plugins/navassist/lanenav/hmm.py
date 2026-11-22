"""Discrete Bayesian (HMM forward) filter over the ego lane index 1..N (from the left).

Each sensor contributes a likelihood vector over lanes; vectors are tempered by
an exponent dt/tau so that time-correlated errors (GPS multipath, a vision model
stuck on the same wrong answer for a second) are not counted 10-20 times a second.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

from .junction_side import SideConfig, SideEvidence, infer_added_left

# Tesla carState lane line codes: tens digit = colour (1 white, 2 yellow, 3 blue), ones = 0 dashed / 1 solid.
YELLOW_SOLID = 21
YELLOW_DASHED = 20
WHITE_SOLID = 11
WHITE_DASHED = 10


@dataclass
class FilterConfig:
  lane_width_m: float = 3.5
  # GPS
  gps_lateral_scale: float = 0.8      # hAcc is a 2-D estimate; lateral 1-sigma ~ 0.8*hAcc (inferred)
  map_sigma_m: float = 1.2            # Amap link geometry vs real carriageway centre (inferred)
  route_bias_m: float = 0.0           # known offset of the polyline from carriageway centre (right +)
  # Route-offset prior (where Amap draws the polyline laterally).
  #  'road_centre': polyline = centre of the road carriageway; junction bays placed by added_left (old).
  #  'recommended': when the recommended lane set is known, polyline = mean centre of the
  #                 recommended lanes; otherwise fall back to 'road_centre'.
  route_offset_mode: str = "road_centre"
  route_offset_sigma_m: float = 0.6   # extra 1-sigma on that offset (unverified on real Amap data)
  route_offset_hug_weight: float = 0.0  # mixture mass for "polyline hugs ONE recommended lane"
  gps_outlier: float = 0.10           # mixture weight of a uniform "GPS is wrong" component
  gps_max_hacc_m: float = 15.0        # above this the fix is ignored entirely
  gps_max_proj_m: float = 25.0        # fix further from the route than this is not on this road
  gps_tau_s: float = 5.0              # GPS error correlation time used for tempering
  # Vision (phone MNN, leftClass/rightClass 1..3 where 3 means ">= 3")
  mnn_hit: float = 0.80
  mnn_tau_s: float = 1.0
  # modelV2 window
  model_consistent: float = 0.85
  model_edge_hit: float = 0.85
  model_tau_s: float = 1.0
  # Line paint
  yellow_left_hit: float = 0.85
  dashed_hit: float = 0.70
  white_solid_hit: float = 0.60
  lines_tau_s: float = 1.0
  paint_ignore_near_junction_m: float = 120.0  # stop lines / solid zones before junctions
  # Motion
  spontaneous_change_per_s: float = 0.01  # unexplained lane change rate (no event seen)
  event_shift_prob: float = 0.90
  # Output
  display_min_prob: float = 0.55
  display_switch_margin: float = 0.15
  # Junction widening / narrowing: which side did lanes appear on when Amap does not say?
  #  'legacy': all added/removed on the LEFT (old behaviour, reproducible)
  #  'fused' : junction_side.infer_added_left (arrows + recommended-set continuity +
  #            road-edge gap jump + GPS exclusion), re-evaluated for a few seconds after
  #            the change once the post-change edge gaps are seen.
  junction_side_mode: str = "legacy"
  junction_side_reeval_s: float = 3.0
  junction_side_rec_max_age_s: float = 30.0


@dataclass
class Observation:
  t: float
  road_lanes: int                       # lane count of the road segment (Amap / road memory)
  junction_lanes: int | None = None     # Amap junctionLanes count, when near an intersection
  junction_added_left: int | None = None  # how many of the extra junction lanes open on the left
  junction_distance_m: float | None = None
  # Amap recommended lanes, 1-based in the ACTIVE numbering (junction lanes near a junction,
  # road lanes otherwise). None/empty = unknown.
  recommended: tuple | None = None
  maneuver: str | None = None
  lane_arrows: tuple | None = None        # per lane (active numbering), tuple of allowed actions
  left_edge_gap_m: float | None = None    # road edge / model window distance, None = not seen
  right_edge_gap_m: float | None = None
  # GPS (already projected onto the route by the caller, or raw via gps_* fields + Route)
  gps_lateral_m: float | None = None
  gps_proj_dist_m: float | None = None
  gps_hacc_m: float | None = None
  # Phone MNN
  mnn_left_class: int | None = None
  mnn_right_class: int | None = None
  # modelV2
  model_visible: int | None = None
  model_ego0: int | None = None
  model_left_edge: bool = False
  model_right_edge: bool = False
  # carState lane-line codes
  left_line: int | None = None
  right_line: int | None = None
  # completed lane change: 'left' / 'right' / None
  lane_change: str | None = None
  extras: dict = field(default_factory=dict)


def _phi(x: float) -> float:
  return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _normalize(v: list[float]) -> list[float]:
  s = sum(v)
  if s <= 0 or not math.isfinite(s):
    return [1.0 / len(v)] * len(v)
  return [x / s for x in v]


def _temper(lik: list[float], power: float) -> list[float]:
  power = max(0.0, min(1.0, power))
  m = max(lik)
  if m <= 0:
    return [1.0] * len(lik)
  return [(x / m) ** power for x in lik]


def _strip_prob(lo: float, hi: float, d: float, sigma: float) -> float:
  return max(0.0, _phi((hi - d) / sigma) - _phi((lo - d) / sigma))


def route_offset_candidates(n: int, recommended, cfg: "FilterConfig") -> list[tuple[float, float]] | None:
  """Where the route polyline lies, measured from the LEFT edge of the active lane layout,
  as (position_m, weight) candidates. None when the recommended set is unusable.

  Main hypothesis: the mean centre of the recommended lanes. With weight
  ``route_offset_hug_weight`` the polyline instead sits on the centre of one of the
  recommended lanes (split evenly), because it is not verified that Amap draws the mean."""
  w = cfg.lane_width_m
  rec = sorted({int(k) for k in (recommended or ()) if isinstance(k, int) and 1 <= int(k) <= n})
  if not rec:
    return None
  centres = [(k - 0.5) * w for k in rec]
  mean = sum(centres) / len(centres)
  h = max(0.0, min(1.0, cfg.route_offset_hug_weight)) if len(rec) > 1 else 0.0
  out = [(mean, 1.0 - h)]
  if h > 0:
    out += [(c, h / len(centres)) for c in centres]
  return out


def gps_likelihood(n: int, lateral_m: float, hacc_m: float, cfg: FilterConfig,
                   road_lanes: int | None = None, extra_left: int = 0,
                   recommended=None) -> list[float]:
  """P(GPS lateral | lane i). Integrates a Gaussian over each lane's strip so the
  vector flattens towards uniform automatically when sigma >> lane width.

  Reference frame of the route polyline:
  * ``route_offset_mode='recommended'`` and a usable ``recommended`` set: the polyline is
    taken to lie on the mean centre of the recommended lanes (plus optional "hugs one
    recommended lane" mixture), with an extra ``route_offset_sigma_m`` of uncertainty.
    This does not need ``road_lanes``/``extra_left`` at all.
  * otherwise (fallback, old behaviour): the polyline is the centre of the *road*
    carriageway (``road_lanes`` wide); at a junction the strip layout is extended by
    ``extra_left`` lanes on the left and the rest on the right."""
  w = cfg.lane_width_m
  cands = route_offset_candidates(n, recommended, cfg) if cfg.route_offset_mode == "recommended" else None
  out = []
  if cands is not None:
    sigma = math.hypot(cfg.gps_lateral_scale * hacc_m, cfg.map_sigma_m, cfg.route_offset_sigma_m)
    for i in range(n):
      lo, hi = i * w, (i + 1) * w
      p = sum(wt * _strip_prob(lo, hi, lateral_m + r, sigma) for r, wt in cands)
      out.append((1.0 - cfg.gps_outlier) * p + cfg.gps_outlier / n)
    return out
  sigma = math.hypot(cfg.gps_lateral_scale * hacc_m, cfg.map_sigma_m)
  # car position relative to the carriageway centre = lateral (vs polyline) + polyline offset
  d = lateral_m + cfg.route_bias_m
  base = road_lanes if road_lanes else n
  left_edge = -base * w / 2.0 - extra_left * w
  for i in range(n):
    lo = left_edge + i * w
    hi = lo + w
    # p(d | lane i) with the car uniformly somewhere inside the lane strip:
    # (Phi((hi-d)/s) - Phi((lo-d)/s)) / w. No tail absorption by the outer lanes,
    # so a fix far outside the road with a large sigma does not "prove" lane 1 or N.
    p = _strip_prob(lo, hi, d, sigma)
    out.append((1.0 - cfg.gps_outlier) * p + cfg.gps_outlier / n)
  return out


def class_likelihood(n: int, cls: int, from_right: bool, hit: float) -> list[float]:
  out = []
  for i in range(1, n + 1):
    k = (n - i + 1) if from_right else i
    out.append(hit if min(k, 3) == cls else (1.0 - hit) / 2.0)
  return out


class LaneFilter:
  def __init__(self, cfg: FilterConfig | None = None):
    self.cfg = cfg or FilterConfig()
    self.n = 0
    self.belief: list[float] = []
    self.t: float | None = None
    self.displayed: int | None = None
    self.last_used: dict = {}
    self._in_junction = False
    self._junction_shift: int | None = None
    # fused junction-side state
    self._edges = deque()          # (t, left_gap, right_gap)
    self._prev_rec = None
    self._prev_rec_tn = None       # (t, lane count) the recommended set was seen under
    self._prev_man = None
    self._pending = None           # provisional side decision awaiting post-change edges
    self.last_side: dict | None = None

  # ----- state-space handling -------------------------------------------------
  def _resize(self, n_new: int, added_left: int | None = None) -> None:
    if n_new == self.n:
      return
    if self.n == 0 or not self.belief:
      self.n, self.belief = n_new, [1.0 / n_new] * n_new
      return
    if added_left is None:
      # Unknown where the lanes appeared/disappeared: anchor to the right edge
      # (Chinese urban junctions mostly add left-turn bays on the left).
      added_left = n_new - self.n
    new = [0.0] * n_new
    for i, p in enumerate(self.belief):
      j = min(n_new - 1, max(0, i + added_left))
      new[j] += p
    # a little diffusion: the mapping itself is uncertain
    eps = 0.05
    self.belief = _normalize([(1 - eps) * x + eps / n_new for x in new])
    self.n = n_new
    if self.displayed is not None:
      self.displayed = min(n_new, max(1, self.displayed + added_left))

  def _shift(self, k: int) -> None:
    """Re-map after a revised side decision: physical lanes move by k indices."""
    if not k or not self.belief:
      return
    n = self.n
    new = [0.0] * n
    for i, p in enumerate(self.belief):
      new[min(n - 1, max(0, i + k))] += p
    self.belief = _normalize(new)
    if self.displayed is not None:
      self.displayed = min(n, max(1, self.displayed + k))

  def _edge_median(self, t0, t1):
    l = sorted(x for t, x, _ in self._edges if t0 <= t <= t1 and x is not None)
    r = sorted(x for t, _, x in self._edges if t0 <= t <= t1 and x is not None)
    seen = [1 for t, _, _ in self._edges if t0 <= t <= t1]
    if len(seen) < 3:
      return None
    # an edge counts as "seen" only if it was visible in at least half of the samples
    lm = l[len(l) // 2] if len(l) * 2 >= len(seen) else None
    rm = r[len(r) // 2] if len(r) * 2 >= len(seen) else None
    return (lm, rm)

  def _side_evidence(self, ob: Observation, n_new: int) -> SideEvidence:
    return SideEvidence(
      n_old=self.n, n_new=n_new,
      old_rec=tuple((self._prev_rec or ()) if self._prev_rec_fresh(ob.t) else ()), new_rec=tuple(ob.recommended or ()),
      same_manoeuvre=bool(ob.maneuver) and ob.maneuver == self._prev_man,
      arrows_new=ob.lane_arrows,
      edge_before=self._edge_median(ob.t - 5.0, ob.t - 0.3),
      gps_lateral_m=ob.gps_lateral_m, gps_hacc_m=ob.gps_hacc_m,
      old_belief=tuple(self.belief) if self.belief else None)

  def _prev_rec_fresh(self, t: float) -> bool:
    """Only compare with a recommended set seen in the SAME numbering (old lane count), recently."""
    if self._prev_rec_tn is None:
      return False
    t0, n0 = self._prev_rec_tn
    return n0 == self.n and t - t0 <= self.cfg.junction_side_rec_max_age_s

  def _side_cfg(self) -> SideConfig:
    return SideConfig(lane_width_m=self.cfg.lane_width_m)

  def _fused_side(self, ob: Observation, n_new: int) -> int:
    ev = self._side_evidence(ob, n_new)
    res = infer_added_left(ev, self._side_cfg())
    self._pending = dict(t0=ob.t, ev=ev, a=res["added_left"])
    self.last_side = dict(res, t=ob.t, n_old=self.n, n_new=n_new, final=False)
    return res["added_left"]

  def _reeval_side(self, ob: Observation) -> None:
    """One re-evaluation, junction_side_reeval_s after the change, with the post-change edges.

    Done once (not continuously) so a noisy edge window cannot make the number flip back and forth.
    """
    pend = self._pending
    if pend is None:
      return
    if self.n != pend["ev"].n_new:
      self._pending = None
      return
    if ob.t - pend["t0"] < self.cfg.junction_side_reeval_s:
      return
    self._pending = None
    after = self._edge_median(pend["t0"] + 0.5, ob.t)
    if self.last_side is not None:
      self.last_side["final"] = True
    if after is None:
      return
    ev = pend["ev"]
    ev.edge_after = after
    res = infer_added_left(ev, self._side_cfg())
    if res["added_left"] != pend["a"]:
      self._shift(res["added_left"] - pend["a"])
      if self._in_junction and self._junction_shift is not None:
        self._junction_shift += res["added_left"] - pend["a"]
    self.last_side = dict(res, t=pend["t0"], n_old=ev.n_old, n_new=ev.n_new, final=True, revised_at=ob.t,
                          first=pend["a"])

  def _predict(self, dt: float, event: str | None) -> None:
    n = self.n
    b = self.belief
    if event in ("left", "right"):
      step = -1 if event == "left" else 1
      p = self.cfg.event_shift_prob
      new = [0.0] * n
      for i, x in enumerate(b):
        j = min(n - 1, max(0, i + step))
        new[j] += p * x
        new[i] += (1 - p) * x
      self.belief = new
      if self.displayed is not None:
        self.displayed = min(n, max(1, self.displayed + step))
      return
    q = min(0.5, self.cfg.spontaneous_change_per_s * max(0.0, dt))
    new = [0.0] * n
    for i, x in enumerate(b):
      nbrs = [j for j in (i - 1, i + 1) if 0 <= j < n]
      new[i] += (1 - q) * x if nbrs else x
      for j in nbrs:
        new[j] += q * x / len(nbrs)
    self.belief = new

  # ----- update ---------------------------------------------------------------
  def update(self, ob: Observation) -> dict:
    cfg = self.cfg
    near_junction = (ob.junction_lanes is not None and ob.junction_lanes >= 1
                     and ob.junction_distance_m is not None)
    n = ob.junction_lanes if near_junction else ob.road_lanes
    if not isinstance(n, int) or n < 1:
      return self.result(valid=False, reason="noLaneCount")
    dt = 0.05 if self.t is None else max(0.0, ob.t - self.t)
    self.t = ob.t
    fused = cfg.junction_side_mode == "fused"
    self._edges.append((ob.t, ob.left_edge_gap_m, ob.right_edge_gap_m))
    while self._edges and ob.t - self._edges[0][0] > 10.0:
      self._edges.popleft()
    if self.n and n != self.n:
      self._pending = None
      if near_junction and not self._in_junction:
        added_left = ob.junction_added_left
        if added_left is None and fused:
          added_left = self._fused_side(ob, n)
        self._junction_shift = added_left
      elif not near_junction and self._in_junction:
        added_left = None if self._junction_shift is None else -self._junction_shift
      else:
        added_left = self._fused_side(ob, n) if fused else None
      self._resize(n, added_left)
    elif not self.n:
      self._resize(n)
    elif fused:
      self._reeval_side(ob)
    if ob.recommended:
      self._prev_rec = tuple(ob.recommended)
      self._prev_rec_tn = (ob.t, self.n)
    if ob.maneuver:
      self._prev_man = ob.maneuver
    self._in_junction = near_junction
    self._predict(dt, ob.lane_change)
    used = {}
    lik = [1.0] * n

    def apply(name, vec, tau):
      nonlocal lik
      v = _temper(vec, dt / tau if tau > 0 else 1.0)
      lik = [a * b for a, b in zip(lik, v)]
      used[name] = v

    extra_left = ob.junction_added_left if near_junction and ob.junction_added_left is not None else (
      (n - ob.road_lanes) if near_junction else 0)
    extra_right = (n - ob.road_lanes - extra_left) if near_junction else 0

    # GPS, weighted by horizontalAccuracy through sigma
    if (ob.gps_lateral_m is not None and ob.gps_hacc_m is not None
        and 0 < ob.gps_hacc_m <= cfg.gps_max_hacc_m
        and (ob.gps_proj_dist_m is None or ob.gps_proj_dist_m <= cfg.gps_max_proj_m)):
      apply("gps", gps_likelihood(n, ob.gps_lateral_m, ob.gps_hacc_m, cfg, ob.road_lanes, extra_left,
                           ob.recommended),
            cfg.gps_tau_s)

    # Phone MNN: lanes counted from each side, saturating at 3. Its corridor is the
    # road, so near a junction with extra bays only the right-hand count stays valid
    # when bays open on the left (and vice versa).
    if ob.mnn_left_class in (1, 2, 3) and extra_left <= 0:
      apply("mnnLeft", class_likelihood(n, ob.mnn_left_class, False, cfg.mnn_hit), cfg.mnn_tau_s)
    if ob.mnn_right_class in (1, 2, 3) and extra_right <= 0:
      apply("mnnRight", class_likelihood(n, ob.mnn_right_class, True, cfg.mnn_hit), cfg.mnn_tau_s)

    # modelV2 window: visible lanes must fit; road edges anchor the window.
    if isinstance(ob.model_visible, int) and isinstance(ob.model_ego0, int) and 0 <= ob.model_ego0 < ob.model_visible:
      left_n, right_n = ob.model_ego0, ob.model_visible - 1 - ob.model_ego0
      vec = []
      for i in range(1, n + 1):
        ok = (i - 1) >= left_n and (n - i) >= right_n
        p = cfg.model_consistent if ok else 1 - cfg.model_consistent
        if ob.model_left_edge:
          p *= cfg.model_edge_hit if i - 1 == left_n else 1 - cfg.model_edge_hit
        if ob.model_right_edge:
          p *= cfg.model_edge_hit if n - i == right_n else 1 - cfg.model_edge_hit
        vec.append(p)
      apply("model", vec, cfg.model_tau_s)

    # Paint: a yellow solid line on the left means the median, i.e. lane 1.
    paint_ok = not (ob.junction_distance_m is not None and ob.junction_distance_m < cfg.paint_ignore_near_junction_m)
    if paint_ok and n >= 2:
      vec = [1.0] * n
      ll, rl = ob.left_line, ob.right_line
      if ll == YELLOW_SOLID:
        vec = [cfg.yellow_left_hit if i == 1 else 1 - cfg.yellow_left_hit for i in range(1, n + 1)]
      elif ll in (WHITE_DASHED, YELLOW_DASHED):
        vec = [a * (1 - cfg.dashed_hit if i == 1 else cfg.dashed_hit) for i, a in zip(range(1, n + 1), vec)]
      elif ll == WHITE_SOLID:
        vec = [a * (cfg.white_solid_hit if i == 1 else 1 - cfg.white_solid_hit) for i, a in zip(range(1, n + 1), vec)]
      if rl in (WHITE_DASHED, YELLOW_DASHED):
        vec = [a * (1 - cfg.dashed_hit if i == n else cfg.dashed_hit) for i, a in zip(range(1, n + 1), vec)]
      elif rl == WHITE_SOLID:
        vec = [a * (cfg.white_solid_hit if i == n else 1 - cfg.white_solid_hit) for i, a in zip(range(1, n + 1), vec)]
      if any(abs(x - vec[0]) > 1e-12 for x in vec):
        apply("lines", vec, cfg.lines_tau_s)

    self.belief = _normalize([b * l for b, l in zip(self.belief, lik)])
    self.last_used = used
    return self.result(valid=True)

  def result(self, valid=True, reason="ok") -> dict:
    if not self.belief:
      return dict(valid=False, reason=reason, lane=None, prob=0.0, belief=(), n=0)
    cfg = self.cfg
    m = max(range(self.n), key=lambda i: self.belief[i])
    pm = self.belief[m]
    # display hysteresis
    if pm >= cfg.display_min_prob:
      if self.displayed is None or self.displayed > self.n:
        self.displayed = m + 1
      elif self.displayed != m + 1 and pm - self.belief[self.displayed - 1] >= cfg.display_switch_margin:
        self.displayed = m + 1
    elif self.displayed is not None and self.belief[self.displayed - 1] < 0.25:
      self.displayed = None
    ent = -sum(p * math.log(p) for p in self.belief if p > 0)
    return dict(valid=valid, reason=reason, lane=self.displayed, map_lane=m + 1, prob=pm,
                entropy=ent, belief=tuple(self.belief), n=self.n, sources=tuple(self.last_used))
