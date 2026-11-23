"""Observation and configuration value objects for the lane filter."""
from __future__ import annotations
from dataclasses import dataclass, field


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
