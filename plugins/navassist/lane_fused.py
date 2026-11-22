"""On-car adapter: run the lanenav fused filter in place of GeometricLaneMatcher.

The public result matches the old geo matcher so runtime/process/phone can keep
using geoValue / geoConfidence / geoReason. Lane numbers in that interface stay
0-based; lanenav itself is 1-based and the conversion happens here.
"""
from __future__ import annotations

from .lanenav.hmm import FilterConfig
from .lanenav.pipeline import Pipeline
from .rec_gate import in_approach_window

LANE_WIDTH_DEFAULT_M = 3.4
LANE_WIDTH_MIN_M = 2.4
LANE_WIDTH_MAX_M = 4.6
JUNCTION_SWITCH_M = 250.0
VERSION = "fnav-1"

# navstate copies wire.LaneGuidance.allowed_actions (int bitmask) into
# lane["allowedActions"]. lanenav expects a tuple of action-name strings.
_ACTION_BITS = (
  (1 << 0, "straight"),
  (1 << 1, "left"),
  (1 << 2, "right"),
  (1 << 3, "uturn"),
  (1 << 4, "u_turn_right"),
  (1 << 5, "bus"),
  (1 << 6, "variable"),
)


def _allowed_actions(value):
  if isinstance(value, int):
    return tuple(name for bit, name in _ACTION_BITS if value & bit)
  if isinstance(value, (list, tuple, set)):
    return tuple(value)
  return ()


def _clamp_width(width_m):
  if isinstance(width_m, (int, float)) and LANE_WIDTH_MIN_M <= float(width_m) <= LANE_WIDTH_MAX_M:
    return float(width_m)
  return LANE_WIDTH_DEFAULT_M


def _lc_event(prev, state, direction):
  """Emit left/right once when the car's lane-change state machine finishes."""
  s = str(state or "").lower()
  d = str(direction or "").lower()
  finishing = "finishing" in s
  ev = None
  if finishing and not prev:
    if "left" in d:
      ev = "left"
    elif "right" in d:
      ev = "right"
  return ev, finishing


class FusedLaneMatcher:
  def __init__(self):
    cfg = FilterConfig()
    cfg.junction_side_mode = "fused"
    cfg.route_offset_mode = "road_centre"
    cfg.lane_width_m = LANE_WIDTH_DEFAULT_M
    self.cfg = cfg
    self.pipe = Pipeline(None, cfg=cfg, source="ublox", use_gps=True, use_vision=True,
                         use_dr=True, announce=False, use_gps_jump=False)
    self._lc_finishing = False
    self.debug = {}

  def _set_width(self, width_m):
    w = _clamp_width(width_m)
    if abs(w - self.cfg.lane_width_m) >= 0.05:
      self.cfg.lane_width_m = w
      self.pipe.dr.w = w
      self.pipe.dr.trigger = 0.70 * w
    return w

  def update(self, *, t, nav, topology, candidate, road_total,
             lane_offset_m, lane_width_m, lane_sigma_m, speed_mps,
             yaw_rate_dps, bearing_deg, route_bearing, lane_change_state,
             lane_change_direction, left_line=None, right_line=None,
             road_kind='unknown'):
    width = self._set_width(lane_width_m)
    lanes = list(nav.get("lanes") or ())
    n_now = int(nav.get("laneTotalCount") or 0)
    if n_now < 2:
      n_now = len(lanes)
    rec0 = tuple(int(l["index"]) for l in lanes
                 if l.get("recommended") is True and isinstance(l.get("index"), int))
    rec1 = tuple(i + 1 for i in rec0) or None
    arrows = tuple(_allowed_actions(l.get("allowedActions")) for l in lanes)
    dist = nav.get("distanceM")
    maneuver = nav.get("maneuver")
    # 接近窗口与规划门槛一致；此前路口拓宽列表不当作当前路编号。
    near = n_now >= 1 and in_approach_window(dist, road_kind, maneuver)
    road_n = road_total if isinstance(road_total, int) and road_total >= 1 else 0
    if road_n < 1:
      near = False
      rec1 = None
    # 还没到接近窗口时，路口推荐车道的编号不属于当前路，不要喂给融合。
    if (not near) and isinstance(road_n, int) and n_now != road_n:
      rec1 = None
    jlanes = []
    if near and n_now >= 1:
      for i in range(n_now):
        item = lanes[i] if i < len(lanes) else {}
        allowed = _allowed_actions(item.get("allowedActions"))
        jlanes.append({
          "index": i + 1,
          "recommended": bool(item.get("recommended")),
          "allowed": allowed,
        })
    ev, self._lc_finishing = _lc_event(self._lc_finishing, lane_change_state, lane_change_direction)

    mnn_left = mnn_right = None
    if (candidate or {}).get("valid"):
      try:
        ln = int(candidate.get("laneNumber"))
        lc = int(candidate.get("laneCount"))
        if 1 <= ln <= lc:
          # phone_lane validates laneNumber == leftClass, count == left+right-1,
          # and both classes saturate at 3.
          mnn_left = min(3, ln)
          mnn_right = min(3, lc - ln + 1)
      except (TypeError, ValueError):
        pass

    ego = topology.get("egoLaneIndexFromLeft")
    vis = topology.get("visibleLaneCount")
    fr = {
      "t": float(t),
      "speed": speed_mps,
      "yaw_rate_dps": yaw_rate_dps,
      "gps_lateral_m": lane_offset_m if isinstance(lane_offset_m, (int, float)) else None,
      "gps_hacc_m": lane_sigma_m if isinstance(lane_sigma_m, (int, float)) else None,
      "route_bearing": route_bearing,
      "gps": {"bearingDeg": bearing_deg} if bearing_deg is not None else None,
      "lane_change": ev,
      "mnn": {"leftClass": mnn_left, "rightClass": mnn_right},
      "model": {
        "visibleLaneCount": vis if isinstance(vis, int) else None,
        "egoLaneIndexFromLeft": ego if isinstance(ego, int) else None,
        "leftRoadEdge": bool(topology.get("leftRoadEdge") or topology.get("leftCarriagewayAnchored")),
        "rightRoadEdge": bool(topology.get("rightRoadEdge") or topology.get("rightCarriagewayAnchored")),
      },
      "lines": {"left": left_line, "right": right_line},
      "edges": {
        "left_gap_m": topology.get("leftEdgeGapM"),
        "right_gap_m": topology.get("rightEdgeGapM"),
      },
      "nav": {
        "road_lanes": int(road_n) if isinstance(road_n, int) and road_n >= 1 else 0,
        "road_recommended": rec1,
        "maneuver": maneuver,
        "junction": {
          "id": maneuver or "junction",
          "distance_m": float(dist) if near else None,
          "lanes": jlanes,
          "added_left": None,
          "maneuver": maneuver,
        } if near and jlanes else None,
      },
    }
    try:
      res = self.pipe.step(fr)
    except Exception as exc:
      self.debug = {"err": type(exc).__name__}
      return {"value": None, "confidence": 0.0, "reason": "fusedError",
              "offsetM": fr["gps_lateral_m"], "laneWidthM": width, "biasAssumed": True,
              "debug": self.debug}

    lane1 = res.get("lane") if res.get("valid") else None  # 1-based or None
    value = (int(lane1) - 1) if isinstance(lane1, int) and lane1 >= 1 else None
    prob = float(res.get("prob") or 0.0) if res.get("valid") else 0.0
    reason = str(res.get("reason") or "ok")
    if not res.get("valid"):
      reason = reason or "invalid"
    side = res.get("side") or {}
    belief = res.get("belief") or ()
    self.debug = {
      "ver": VERSION,
      "lane1": lane1,
      "n": res.get("n") if road_n >= 1 else 0,
      "prob": round(prob, 3),
      "reason": reason,
      "belief": tuple(round(float(x), 3) for x in belief),
      "map_lane": res.get("map_lane"),
      "sources": tuple(res.get("sources") or ()),
      "dr_lat": None if res.get("dr_lat") is None else round(float(res["dr_lat"]), 3),
      "dr_heading": None if res.get("dr_heading") is None else round(float(res["dr_heading"]), 2),
      "route_bearing": None if res.get("route_bearing") is None else round(float(res["route_bearing"]), 2),
      "lc": ev,
      "side_added": side.get("added_left"),
      "side_conf": side.get("confidence"),
      "side_why": side.get("evidence"),
      "side_final": side.get("final"),
      "n_old": side.get("n_old"),
      "n_new": side.get("n_new"),
      "road_n": road_n,
      "near": int(bool(near)),
      "width": round(width, 2),
      "off": None if fr["gps_lateral_m"] is None else round(float(fr["gps_lateral_m"]), 2),
      "hacc": None if fr["gps_hacc_m"] is None else round(float(fr["gps_hacc_m"]), 2),
      "yaw": None if yaw_rate_dps is None else round(float(yaw_rate_dps), 2),
      "hdg": None if bearing_deg is None else round(float(bearing_deg), 2),
      "mnn": "%s/%s" % ("-" if mnn_left is None else mnn_left, "-" if mnn_right is None else mnn_right),
      "arr": 1 if any(arrows) else 0,
    }
    return {
      "value": value,
      "confidence": round(prob, 2),
      "reason": "fused:" + reason,
      "offsetM": self.debug["off"],
      "laneWidthM": width,
      "biasAssumed": True,
      "debug": self.debug,
    }
