"""Which side did lanes appear on / disappear from when the lane count changes?

Multi-evidence fusion over the hypothesis a = number of lanes added on the LEFT
(widening: 0..delta; narrowing: delta..0, i.e. -a lanes removed on the left).
Every evidence term is a log-score over the candidates; missing evidence adds 0.

  arrows   Amap per-lane turn arrows of the new layout: added lanes on the left are
           expected to be left/U-turn-only, added lanes on the right right-only.
  rec      continuity of the Amap recommended set for the same manoeuvre: physical
           lanes keep their recommendation, so old_rec + a should equal new_rec.
  edge     road-edge / model-window gap jump: the side where lanes were added gets
           farther (gap grows ~a*W on the left, ~(delta-a)*W on the right).
  gps      exclusion only: the implied new lane must not be wildly inconsistent with
           the GPS lateral offset. sigma = hypot(0.8*hAcc, slow bias, route-line error)
           and the score is floored, so GPS can veto absurd numbers but never decide.
  prior    tiny tie-break towards the legacy assumption (all on the left).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

LEFT_ACTIONS = {"left", "uturn", "u_turn", "turn_left", "u_turn_left"}
RIGHT_ACTIONS = {"right", "turn_right", "u_turn_right"}


@dataclass
class SideEvidence:
  n_old: int
  n_new: int
  old_rec: tuple = ()            # 1-based, old numbering
  new_rec: tuple = ()            # 1-based, new numbering
  same_manoeuvre: bool = False
  arrows_new: tuple | None = None  # per new lane, tuple of allowed actions (left->right)
  edge_before: tuple | None = None  # (left_gap_m, right_gap_m); None entries = no edge seen
  edge_after: tuple | None = None
  gps_lateral_m: float | None = None  # car vs route polyline, right +
  gps_hacc_m: float | None = None
  old_belief: tuple | None = None     # belief over old lanes (index 0 = lane 1)


@dataclass
class SideConfig:
  lane_width_m: float = 3.5
  w_arrows: float = 1.5
  w_rec: float = 2.0
  w_edge: float = 1.2
  edge_sigma_lanes: float = 0.6
  edge_z_clip: float = 2.0         # per-side z is clipped (edge gaps are logged in whole metres)
  edge_min_fit: float = -1.125     # best candidate must fit within ~1.5 sigma, else edge term dropped
  gps_bias_m: float = 1.0          # slow GNSS bias seen on real drives (~1 m)
  gps_line_sigma_m: float = 1.8    # Amap route-line error seen on real drives
  gps_floor: float = 0.15          # GPS never pushes a candidate below this likelihood
  w_prior_legacy: float = 0.05


def candidates(n_old: int, n_new: int) -> list[int]:
  d = n_new - n_old
  return list(range(min(0, d), max(0, d) + 1))


def _arrows_score(a: int, ev: SideEvidence) -> float | None:
  """Turn-only lanes grow from the edges: L = left/U-turn-only lanes contiguous from the
  left edge, R = right-only lanes contiguous from the right edge. Added lanes are most
  likely those turn bays: a in [min(d,L), d-min(d,R)] scores 0, every lane outside -1/d."""
  if not ev.arrows_new or len(ev.arrows_new) != ev.n_new:
    return None
  d = ev.n_new - ev.n_old
  if d <= 0:
    return None  # removed lanes are not in the new list: arrows say nothing
  acts = [set(x or ()) for x in ev.arrows_new]
  if not any(acts):
    return None
  L = 0
  while L < ev.n_new and acts[L] and acts[L] <= LEFT_ACTIONS:
    L += 1
  R = 0
  while R < ev.n_new and acts[ev.n_new - 1 - R] and acts[ev.n_new - 1 - R] <= RIGHT_ACTIONS:
    R += 1
  tl, tr = min(d, L), min(d, R)
  if L == 0 and R == 0:
    return None
  if tl + tr <= d:
    lo, hi = tl, d - tr
  else:  # both edges have more turn-only lanes than were added: split by proportion
    lo = hi = round(d * L / (L + R))
  dist = (lo - a) if a < lo else (a - hi if a > hi else 0)
  return -dist / d


def _rec_score(a: int, ev: SideEvidence) -> float | None:
  if not (ev.same_manoeuvre and ev.old_rec and ev.new_rec):
    return None
  shifted = {k + a for k in ev.old_rec if 1 <= k + a <= ev.n_new}
  new = set(ev.new_rec)
  if not shifted and not new:
    return None
  j = len(shifted & new) / len(shifted | new)
  return 2.0 * j - 1.0


def _edge_score(a: int, ev: SideEvidence, cfg: SideConfig) -> float | None:
  if not ev.edge_before or not ev.edge_after:
    return None
  w = cfg.lane_width_m
  d = ev.n_new - ev.n_old
  deltas = []
  for side in (0, 1):
    b, af = ev.edge_before[side], ev.edge_after[side]
    if b is None and af is None:
      deltas.append(None)
    elif b is not None and af is None:
      deltas.append(w if d > 0 else None)   # edge went out of view: got farther (only meaningful when widening)
    elif b is None and af is not None:
      deltas.append(-w if d < 0 else None)  # edge appeared: got nearer
    else:
      deltas.append(af - b)
  if deltas[0] is None and deltas[1] is None:
    return None
  exp_l, exp_r = a * w, (d - a) * w
  s, k = 0.0, 0
  for got, exp in ((deltas[0], exp_l), (deltas[1], exp_r)):
    if got is None:
      continue
    z = min(cfg.edge_z_clip, abs(got - exp) / (cfg.edge_sigma_lanes * w))  # robust: one bad side can't veto
    s += -0.5 * z * z
    k += 1
  return s / k


def _gps_score(a: int, ev: SideEvidence, cfg: SideConfig) -> float | None:
  if ev.gps_lateral_m is None or ev.old_belief is None or not ev.old_belief:
    return None
  w = cfg.lane_width_m
  k_old = max(range(len(ev.old_belief)), key=lambda i: ev.old_belief[i])  # 0-based
  k_new = k_old + a
  if not 0 <= k_new < ev.n_new:
    return math.log(cfg.gps_floor)
  hacc = ev.gps_hacc_m if ev.gps_hacc_m and ev.gps_hacc_m > 0 else 3.0
  sigma = math.hypot(0.8 * hacc, cfg.gps_bias_m, cfg.gps_line_sigma_m)
  centre = (k_new - (ev.n_new - 1) / 2.0) * w      # polyline assumed at the new road centre
  r = ev.gps_lateral_m - centre
  return math.log(max(cfg.gps_floor, math.exp(-0.5 * (r / sigma) ** 2)))


def infer_added_left(ev: SideEvidence, cfg: SideConfig | None = None) -> dict:
  cfg = cfg or SideConfig()
  cands = candidates(ev.n_old, ev.n_new)
  d = ev.n_new - ev.n_old
  terms = {}
  scores = {}
  # Edge gaps that fit NO candidate (e.g. both gaps shrank while widening: the 4-line window
  # re-anchored in the junction) carry no side information -> drop the edge term.
  edge_all = {a: _edge_score(a, ev, cfg) for a in cands}
  edge_ok = all(v is not None for v in edge_all.values()) and max(edge_all.values()) >= cfg.edge_min_fit
  for a in cands:
    tot = cfg.w_prior_legacy if a == d else 0.0
    parts = {}
    for name, fn, wgt in (("arrows", lambda: _arrows_score(a, ev), cfg.w_arrows),
                          ("rec", lambda: _rec_score(a, ev), cfg.w_rec),
                          ("edge", lambda: edge_all[a] if edge_ok else None, cfg.w_edge),
                          ("gps", lambda: _gps_score(a, ev, cfg), 1.0)):
      v = fn()
      if v is not None:
        parts[name] = round(wgt * v, 3)
        tot += wgt * v
    scores[a] = tot
    terms[a] = parts
  m = max(scores.values())
  z = sum(math.exp(s - m) for s in scores.values())
  post = {a: math.exp(s - m) / z for a, s in scores.items()}
  best = max(cands, key=lambda a: (post[a], a == d))
  used = sorted({k for p in terms.values() for k in p})
  return dict(added_left=best, confidence=round(post[best], 3), posterior={a: round(p, 3) for a, p in post.items()},
              evidence=used, terms=terms, delta=d)
