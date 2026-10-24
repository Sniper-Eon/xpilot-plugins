from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from .controller import TrafficControlPhase

# CP's low-speed cruise acceleration envelope. This applies only to a
# same-event CAN-authoritative green start and remains time/speed bounded.
START_MAX_ACCEL = 1.6
START_MAX_SPEED = 2.5
START_MAX_DURATION_NS = 3_000_000_000
START_JERK_LIMIT = 1.0
START_NEAR_LEAD_DISTANCE = 8.0
START_LEAD_CONFIRM_NS = 500_000_000
START_LEAD_CLEAR_NS = 400_000_000
START_LEAD_MAX_GAP_NS = 150_000_000
QUEUE_STOP_LINE_GUARD = 5.0
MOVING_GREEN_SPEED = 0.3
TERMINAL_MAX_SPEED = 1.5
TERMINAL_LOOKAHEAD_S = 0.05
PLANNER_TRAFFIC_STALE_NS = 350_000_000
MAX_TRAFFIC_STOP_BRAKE = 3.0
YELLOW_MARGIN_BASE = 1.0
YELLOW_MARGIN_TIME = 0.15
YELLOW_MARGIN_MIN = 2.0
YELLOW_MARGIN_MAX = 4.0
STOP_CONTROL_PHASES = (
  int(TrafficControlPhase.approachRed),
  int(TrafficControlPhase.braking),
  int(TrafficControlPhase.hold),
  int(TrafficControlPhase.flashingGreenStop),
  int(TrafficControlPhase.yellowStop),
)


@dataclass(frozen=True)
class _TrafficStopStyle:
  comfort_brake: float
  jerk_limit: float
  decel_margin: float


class TrafficPlanAction(IntEnum):
  none = 0
  stop = 1
  hold = 2
  start = 3
  release = 4
  rollingRelease = 5


class TrafficStartBlockReason(IntEnum):
  none = 0
  noPreviousHold = 1
  eventMismatch = 2
  unsafeBasePlan = 3
  modelStop = 4
  driverOverride = 5
  physicalLead = 6
  invalidCruise = 7
  alreadyStarted = 8


@dataclass
class TrafficPlanDiagnostics:
  mode: int = 0
  action: TrafficPlanAction = TrafficPlanAction.none
  applied: bool = False
  start_requested: bool = False
  start_applied: bool = False
  start_block_reason: TrafficStartBlockReason = TrafficStartBlockReason.none
  event_id: int = 0
  stop_session_id: int = 0
  direction_unknown: bool = False
  driver_override_active: bool = False
  can_remaining: float = 0.0
  station_innovation: float = 0.0
  stop_control_allowed: bool = False
  stop_safety_allowed: bool = False
  raw_observation_fresh: bool = False
  raw_observation_age_ms: float = 0.0
  stop_direction_unknown: bool = False
  phase: int = int(TrafficControlPhase.off)
  light_state: int = 0
  remaining_distance: float = 0.0
  raw_distance: float = 255.0
  stop_reference: float = 0.0
  source_bus: int = 0
  quality: int = 0
  base_a_target: float = 0.0
  traffic_a_target: float = 0.0
  final_a_target: float = 0.0
  should_stop: bool = False
  terminal_catch_active: bool = False


class TrafficDiagnosticsMixin:
  """Copy trafficRadarState into TrafficPlanDiagnostics and out to longitudinalPlanSP."""

  def _set_diagnostics_from_traffic(self, traffic) -> None:
    if traffic is None:
      return
    self.diagnostics.event_id = int(traffic.eventId)
    self.diagnostics.stop_session_id = int(traffic.stopSessionId)
    self.diagnostics.direction_unknown = bool(traffic.directionUnknown)
    self.diagnostics.driver_override_active = bool(traffic.driverOverrideActive)
    self.diagnostics.can_remaining = float(traffic.canRemaining)
    self.diagnostics.station_innovation = float(traffic.stationInnovation)
    self.diagnostics.stop_control_allowed = bool(traffic.stopControlAllowed)
    self.diagnostics.stop_safety_allowed = bool(traffic.stopSafetyAllowed)
    self.diagnostics.raw_observation_fresh = bool(traffic.rawObservationFresh)
    self.diagnostics.raw_observation_age_ms = float(traffic.observationAgeMs)
    self.diagnostics.stop_direction_unknown = bool(traffic.stopDirectionUnknown)
    self.diagnostics.mode = int(traffic.mode)
    self.diagnostics.phase = int(traffic.phase)
    self.diagnostics.light_state = int(traffic.lightState)
    self.diagnostics.remaining_distance = max(0.0, float(traffic.distanceToStopPoint))
    self.diagnostics.raw_distance = float(traffic.rawDistance)
    self.diagnostics.stop_reference = max(
      0.0, float(traffic.oemTargetDistance) - float(traffic.distanceToStopPoint),
    )
    self.diagnostics.source_bus = int(traffic.sourceBus)
    self.diagnostics.quality = int(traffic.quality)


  def annotate_plan_sp(self, plan_sp) -> None:
    diagnostics = self.diagnostics
    plan_sp.aTarget = diagnostics.final_a_target
    target = plan_sp.teslaTrafficControl
    target.mode = diagnostics.mode
    target.phase = diagnostics.phase
    target.active = diagnostics.action != TrafficPlanAction.none
    target.shadow = False
    target.applied = diagnostics.applied
    target.shouldStop = diagnostics.should_stop
    target.remainingDistance = diagnostics.remaining_distance
    target.rawDistance = diagnostics.raw_distance
    target.stopReference = diagnostics.stop_reference
    target.lightState = diagnostics.light_state
    target.sourceBus = diagnostics.source_bus
    target.quality = diagnostics.quality
    target.constraintAccel = diagnostics.traffic_a_target
    target.action = int(diagnostics.action)
    target.baseATarget = diagnostics.base_a_target
    target.finalATarget = diagnostics.final_a_target
    target.startRequested = diagnostics.start_requested
    target.startApplied = diagnostics.start_applied
    target.startBlockReason = int(diagnostics.start_block_reason)
    target.eventId = diagnostics.event_id
    target.terminalCatchActive = diagnostics.terminal_catch_active
    target.stopSessionId = diagnostics.stop_session_id
    target.directionUnknown = diagnostics.direction_unknown
    target.driverOverrideActive = diagnostics.driver_override_active
    target.canRemaining = diagnostics.can_remaining
    target.stationInnovation = diagnostics.station_innovation
    target.stopControlAllowed = diagnostics.stop_control_allowed
    target.stopSafetyAllowed = diagnostics.stop_safety_allowed
    target.rawObservationFresh = diagnostics.raw_observation_fresh
    target.rawObservationAgeMs = diagnostics.raw_observation_age_ms
    target.stopDirectionUnknown = diagnostics.stop_direction_unknown

