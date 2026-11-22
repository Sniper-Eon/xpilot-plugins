"""Reference single-source lane numbering used for comparison only."""
from __future__ import annotations


def mnn_only(ob) -> int | None:
  """Phone-vision rule as in navassist df5fce5 S7 (phoneLeft): laneNumber = leftClass,
  clamped to the road's lane count. leftClass saturates at 3."""
  n = ob.junction_lanes if (ob.junction_lanes and ob.junction_distance_m is not None) else ob.road_lanes
  if ob.mnn_left_class in (1, 2, 3) and ob.mnn_right_class in (1, 2, 3) and n:
    return min(ob.mnn_left_class, n)
  return None


def gps_only(ob, lane_width_m=3.5, max_hacc_m=25.0, route_bias_m=0.0) -> int | None:
  """Naive satellite lane numbering: nearest lane centre to the projected lateral offset.
  Accepts fixes up to 25 m hAcc (the gate gpsfeed.py uses for forwarding)."""
  n = ob.junction_lanes if (ob.junction_lanes and ob.junction_distance_m is not None) else ob.road_lanes
  if ob.gps_lateral_m is None or ob.gps_hacc_m is None or not n or ob.gps_hacc_m > max_hacc_m:
    return None
  d = ob.gps_lateral_m + route_bias_m  # polyline offset (right +) -> carriageway frame
  near = bool(ob.junction_lanes and ob.junction_distance_m is not None)
  extra_left = (ob.junction_added_left if ob.junction_added_left is not None else n - ob.road_lanes) if near else 0
  left_edge = -ob.road_lanes * lane_width_m / 2.0 - extra_left * lane_width_m
  i = int((d - left_edge) // lane_width_m) + 1
  return max(1, min(n, i))
