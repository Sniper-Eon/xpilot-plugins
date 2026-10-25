"""Shared TN tuning values and migration keys; extracted without numerical changes."""
from dataclasses import asdict, dataclass

@dataclass(frozen=True)
class LongitudinalTuning:
  t_follow_relaxed: float = 1.75
  t_follow_standard: float = 1.45
  t_follow_aggressive: float = 1.25
  x_ego_obstacle_cost: float = 3.0
  j_ego_cost: float = 5.0
  a_change_cost: float = 200.0
  danger_zone_cost: float = 100.0
  lead_danger_factor: float = 0.75
  comfort_brake: float = 2.5
  stop_distance: float = 6.0
  jerk_factor_relaxed: float = 1.0

  def as_dict(self) -> dict[str, float]:
    return asdict(self)


DEFAULT_VALUES = LongitudinalTuning().as_dict()
CRAZYMAX_VALUES = {
  **DEFAULT_VALUES,
  "x_ego_obstacle_cost": 5.0,
  "j_ego_cost": 3.0,
  "a_change_cost": 100.0,
  "danger_zone_cost": 80.0,
  "lead_danger_factor": 0.35,
  "comfort_brake": 2.7,
  "stop_distance": 4.5,
  "jerk_factor_relaxed": 0.8,
  "t_follow_relaxed": 1.65,
  "t_follow_standard": 1.35,
  "t_follow_aggressive": 1.0,
}

# (minimum, maximum, quantization step, maximum change per second). All values
# are the old C3XL controls expressed in native units instead of hundredths.
VALUE_SPECS = {
  "t_follow_relaxed": (0.50, 4.00, 0.01, 0.20),
  "t_follow_standard": (0.50, 4.00, 0.01, 0.20),
  "t_follow_aggressive": (0.50, 4.00, 0.01, 0.20),
  "x_ego_obstacle_cost": (0.01, 10.0, 0.01, 2.0),
  "j_ego_cost": (0.01, 10.0, 0.01, 2.0),
  "a_change_cost": (0.01, 500.0, 0.01, 100.0),
  "danger_zone_cost": (0.01, 500.0, 0.01, 100.0),
  "lead_danger_factor": (0.01, 5.0, 0.01, 1.0),
  "comfort_brake": (0.50, 5.0, 0.01, 0.25),
  "stop_distance": (1.0, 12.0, 0.01, 0.50),
  "jerk_factor_relaxed": (0.01, 3.0, 0.01, 1.0),
}

RS408_SEMANTIC_TO_NATIVE = {
  "following.time.relaxed_s": "t_follow_relaxed",
  "following.time.standard_s": "t_follow_standard",
  "following.time.aggressive_s": "t_follow_aggressive",
  "mpc.obstacle_cost": "x_ego_obstacle_cost",
  "mpc.jerk_cost": "j_ego_cost",
  "mpc.accel_change_cost": "a_change_cost",
  "mpc.danger_zone_cost": "danger_zone_cost",
  "mpc.lead_danger_factor": "lead_danger_factor",
  "mpc.obstacle_comfort_brake_mps2": "comfort_brake",
  "mpc.obstacle_stop_distance_m": "stop_distance",
  "mpc.jerk_factor.relaxed": "jerk_factor_relaxed",
}
RS408_SHARED_IDS = frozenset(key for key in RS408_SEMANTIC_TO_NATIVE if key.startswith("following."))
RS408_FAMILY_IDS = frozenset(RS408_SEMANTIC_TO_NATIVE) - RS408_SHARED_IDS
RS408_SLUGS = {
  "sp_upstream_tunable": "official",
  "local": "experimental",
  "tn_no_dec": "tn_no_dec",
}
RS408_TN_NATIVE_IDS = frozenset({"tn.accel_personality.enabled", "tn.accel_personality.profile"})


