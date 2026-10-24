from __future__ import annotations

import math

import numpy as np

from openpilot.cereal import log
from openpilot.selfdrive.car.cruise import V_CRUISE_UNSET
from .arbitrator_types import (
  QUEUE_STOP_LINE_GUARD,
  START_LEAD_CLEAR_NS,
  START_LEAD_CONFIRM_NS,
  START_LEAD_MAX_GAP_NS,
  START_MAX_ACCEL,
  START_MAX_DURATION_NS,
  START_MAX_SPEED,
  START_NEAR_LEAD_DISTANCE,
  TrafficPlanAction,
  TrafficStartBlockReason,
)
from .stop_profile import StopProfileGenerator


class StartPlanMixin:
  """Lead-vehicle GO gate, queue-follow ownership and same-session green START."""

  @staticmethod
  def _base_plan_lead_source(plan) -> int | None:
    source = getattr(
      plan, "longitudinalPlanSource", log.LongitudinalPlan.LongitudinalPlanSource.cruise,
    )
    source = int(getattr(source, "raw", source))
    return source if source in (
      int(log.LongitudinalPlan.LongitudinalPlanSource.lead0),
      int(log.LongitudinalPlan.LongitudinalPlanSource.lead1),
      int(log.LongitudinalPlan.LongitudinalPlanSource.lead2),
    ) else None

  @classmethod
  def _lead_gate_state(cls, plan, sm) -> tuple[bool, bool, bool]:
    lead_source = cls._base_plan_lead_source(plan)
    if "radarState" not in sm.seen or not cls._healthy(sm, "radarState"):
      return False, False, False
    radar_state = sm["radarState"]
    blocking_near = []
    confirmable_near = []
    for lead in (radar_state.leadOne, radar_state.leadTwo):
      if not bool(getattr(lead, "present", False)):
        blocking_near.append(False)
        confirmable_near.append(False)
        continue
      d_rel = float(getattr(lead, "dRel", float("nan")))
      # A malformed current lead is uncertain and therefore blocks this GO
      # cycle, but it can never permanently own a stop session.
      valid_distance = bool(np.isfinite(d_rel) and d_rel > 0.0)
      blocking_near.append(not valid_distance or d_rel <= START_NEAR_LEAD_DISTANCE)
      confirmable_near.append(valid_distance and d_rel <= START_NEAR_LEAD_DISTANCE)
    any_near = any(blocking_near)
    selected_near = bool(
      (lead_source == int(log.LongitudinalPlan.LongitudinalPlanSource.lead0) and confirmable_near[0])
      or (lead_source == int(log.LongitudinalPlan.LongitudinalPlanSource.lead1) and confirmable_near[1])
      or (lead_source == int(log.LongitudinalPlan.LongitudinalPlanSource.lead2) and any(confirmable_near))
    )
    return True, any_near, selected_near

  def _update_go_lead_gate(self, plan, sm, session_id: int, now_ns: int) -> bool:
    tracked_ids = (
      self._lead_delegated_session_id, self._lead_candidate_session_id,
      self._near_lead_blocked_session_id,
    )
    if any(tracked not in (0, session_id) for tracked in tracked_ids):
      self._reset_lead_gate()

    healthy, any_near, selected_near = self._lead_gate_state(plan, sm)
    if not healthy:
      self._lead_clear_since_ns = 0
      self._lead_clear_last_ns = 0
      self._lead_candidate_since_ns = 0
      self._lead_candidate_last_ns = 0
      return False

    if any_near:
      self._near_lead_blocked_session_id = session_id
      self._lead_clear_since_ns = 0
      self._lead_clear_last_ns = 0
    elif self._near_lead_blocked_session_id == session_id:
      if (self._lead_clear_since_ns == 0 or self._lead_clear_last_ns == 0
          or now_ns - self._lead_clear_last_ns > START_LEAD_MAX_GAP_NS):
        self._lead_clear_since_ns = now_ns
      self._lead_clear_last_ns = now_ns
      if now_ns - self._lead_clear_since_ns >= START_LEAD_CLEAR_NS:
        self._near_lead_blocked_session_id = 0
        self._lead_clear_since_ns = 0
        self._lead_clear_last_ns = 0

    if selected_near:
      if (self._lead_candidate_session_id != session_id or self._lead_candidate_since_ns == 0
          or self._lead_candidate_last_ns == 0
          or now_ns - self._lead_candidate_last_ns > START_LEAD_MAX_GAP_NS):
        self._lead_candidate_session_id = session_id
        self._lead_candidate_since_ns = now_ns
      self._lead_candidate_last_ns = now_ns
      if now_ns - self._lead_candidate_since_ns >= START_LEAD_CONFIRM_NS:
        self._lead_delegated_session_id = session_id
    else:
      self._lead_candidate_session_id = 0
      self._lead_candidate_since_ns = 0
      self._lead_candidate_last_ns = 0
    return True

  def _go_lead_blocked(self, plan, sm, session_id: int, now_ns: int) -> bool:
    healthy = self._update_go_lead_gate(plan, sm, session_id, now_ns)
    return bool(
      not healthy
      or self._lead_delegated_session_id == session_id
      or self._near_lead_blocked_session_id == session_id
    )

  def _queue_stop_guard_distance(self, sm) -> float:
    raw_v_ego = float(sm["carState"].vEgo)
    a_ego = float(sm["carState"].aEgo)
    if not math.isfinite(raw_v_ego) or not math.isfinite(a_ego):
      return 200.0
    v_ego = max(0.0, raw_v_ego)
    style = self._base_stop_style(sm)
    braking_distance = StopProfileGenerator.required_stop_distance(
      v_ego=v_ego, a_ego=a_ego,
      actuator_delay=self._actuator_delay + 0.2,
      max_brake=style.comfort_brake,
      jerk_limit=style.jerk_limit * self._speed_jerk_scale(v_ego),
    )
    return float(np.clip(max(QUEUE_STOP_LINE_GUARD, braking_distance),
                         QUEUE_STOP_LINE_GUARD, 200.0))

  def _queue_follow_owns_motion(self, plan, sm, traffic, now_ns: int) -> bool:
    session_id = int(traffic.stopSessionId)
    return bool(
      session_id > 0
      and self._lead_delegated_session_id == session_id
      # STOP queue ownership requires a currently healthy, fully reconfirmed
      # selected near lead. The permanent session bit remains only a GO veto;
      # it cannot by itself release a red-light STOP for a stale/far lead slot.
      and self._lead_candidate_session_id == session_id
      and self._lead_candidate_since_ns > 0
      and now_ns - self._lead_candidate_since_ns >= START_LEAD_CONFIRM_NS
      and float(traffic.distanceToStopPoint) > self._queue_stop_guard_distance(sm)
      and bool(getattr(plan, "hasLead", False))
      and self._base_plan_lead_source(plan) is not None
      and "radarState" in sm.seen and self._healthy(sm, "radarState")
    )

  def _start_block_reason(self, plan, sm, traffic, now_ns: int) -> TrafficStartBlockReason:
    session_id = int(traffic.stopSessionId)
    if session_id == 0:
      return TrafficStartBlockReason.noPreviousHold
    if session_id not in (self._held_session_id, self._owned_stop_session_id, self._seen_stop_session_id):
      return TrafficStartBlockReason.eventMismatch
    if self._completed_start_session_id == session_id:
      return TrafficStartBlockReason.alreadyStarted
    # OEM green may clear a model-only traffic STOP, but never a driver
    # no-response/soft-disable deceleration or an unknown safety state.
    if ("controlsState" not in sm.seen or not self._healthy(sm, "controlsState")
        or sm["controlsState"].forceDecel):
      return TrafficStartBlockReason.unsafeBasePlan
    if not self._driver_allows_start(sm):
      return TrafficStartBlockReason.driverOverride
    if self._go_lead_blocked(plan, sm, session_id, now_ns):
      return TrafficStartBlockReason.physicalLead
    # A same-event OEM CAN green is authoritative over a model/base-plan
    # traffic-stop residue, matching CP's e2eStopped -> e2eCruise transition.
    # Session, driver, direction, cruise, speed, and duration gates remain.
    v_cruise = float(sm["carState"].vCruise)
    if not 0.0 < v_cruise < V_CRUISE_UNSET:
      return TrafficStartBlockReason.invalidCruise
    return TrafficStartBlockReason.none

  def _finish_start(self, session_id: int) -> None:
    self._completed_start_session_id = session_id
    self._active_start_session_id = 0
    self._start_started_ns = 0

  def _apply_start(self, plan, sm, traffic, now_ns: int) -> bool:
    self.diagnostics.start_requested = True
    session_id = int(traffic.stopSessionId)
    block_reason = self._start_block_reason(plan, sm, traffic, now_ns)
    self.diagnostics.start_block_reason = block_reason
    if block_reason != TrafficStartBlockReason.none:
      if (block_reason != TrafficStartBlockReason.physicalLead
          and self._active_start_session_id == session_id):
        self._finish_start(session_id)
      return False

    self._hold_latched = False
    self._hold_latched_should_stop = False

    v_ego = float(sm["carState"].vEgo)
    if v_ego >= START_MAX_SPEED:
      self._finish_start(session_id)
      return False
    if self._active_start_session_id == 0:
      self._active_start_session_id = session_id
      self._start_started_ns = now_ns
    elif self._active_start_session_id != session_id:
      return False
    if now_ns - self._start_started_ns >= START_MAX_DURATION_NS:
      self._finish_start(session_id)
      return False
    base_a_target = float(plan.aTarget)
    requested_accel = float(np.clip(float(sm["carState"].vCruise) / 3.6 - v_ego, 0.0, START_MAX_ACCEL))
    if requested_accel <= 0.0:
      return False

    times = self._times(len(plan.speeds))
    start_speeds, start_accels, _ = self._profile.build_release(
      v_ego=v_ego, base_accel=requested_accel, times=times,
      preserve_positive_accel=True,
    )
    start_a_target = float(np.interp(self._actuator_delay + 0.05, times, start_accels))
    final_a_target = float(np.clip(max(base_a_target, start_a_target), 0.0, START_MAX_ACCEL))

    plan.speeds = start_speeds.tolist()
    plan.accels = start_accels.tolist()
    plan.jerks = self._padded_jerks(start_accels, times, len(plan.jerks)).tolist()
    plan.aTarget = final_a_target
    plan.shouldStop = False
    plan.allowThrottle = bool(plan.allowThrottle)

    self._was_stopping = False
    self.diagnostics.action = TrafficPlanAction.start
    self.diagnostics.applied = True
    self.diagnostics.start_applied = True
    self.diagnostics.traffic_a_target = start_a_target
    return True

