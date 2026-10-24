from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from .tesla_observer import TRAFFIC_CONTROL_MAX_DISTANCE

STOP_EVIDENCE_LOSS_GRACE_S = 2.0


class TrafficControlMode(IntEnum):
  off = 0
  observe = 1  # Legacy diagnostic mode; the production switch no longer selects it.
  shadow = 2
  stopOnly = 3
  stopGo = 4


class TrafficControlPhase(IntEnum):
  off = 0
  redCandidate = 1
  approachRed = 2
  braking = 3
  hold = 4
  goCandidate = 5
  release = 6
  bypass = 7
  greenFlashCandidate = 8
  flashingGreenStop = 9
  yellowStop = 10
  yellowPass = 11
  lateRed = 12
  passed = 13


@dataclass
class TrafficControlConfig:
  mode: TrafficControlMode = TrafficControlMode.off
  default_stop_reference: float = 5.0
  comfort_brake: float = 2.4
  release_s: float = 3.0
  stationary_release_s: float = 10.0
  driver_override_cooldown_s: float = 0.75
  critical_observation_dropout_s: float = STOP_EVIDENCE_LOSS_GRACE_S
  candidate_dropout_s: float = 2.5
  max_control_distance: float = TRAFFIC_CONTROL_MAX_DISTANCE
  candidate_distance_tolerance: float = 6.0
  candidate_distance_tolerance_ratio: float = 0.08
  max_control_speed: float = float("inf")
  yellow_stop_decel: float = 2.2
  yellow_pass_decel: float = 3.0
  flash_interval_min_s: float = 0.5
  flash_interval_max_s: float = 1.5
  flash_min_half_cycle_s: float = 0.15
  far_candidate_confirm_s: float = 0.5
  farther_replacement_confirm_s: float = 1.0


@dataclass(frozen=True)
class TrafficControlDecision:
  mode: TrafficControlMode
  phase: TrafficControlPhase
  active: bool
  apply_constraint: bool
  shadow: bool
  should_stop: bool
  remaining_distance: float
  stop_reference: float
  light_state: int
  source_bus: int
  quality: int
  stop_session_id: int = 0
  driver_override_active: bool = False
  direction_unknown: bool = False
  can_remaining: float = 0.0
  station_innovation: float = 0.0
  stop_control_allowed: bool = False
  stop_safety_allowed: bool = False
  raw_observation_fresh: bool = False
  stop_direction_unknown: bool = False

