from __future__ import annotations

import math

import numpy as np

from openpilot.cereal import log
from openpilot.selfdrive.modeld.constants import ModelConstants
from .arbitrator_types import (
  MAX_TRAFFIC_STOP_BRAKE,
  TERMINAL_LOOKAHEAD_S,
  TERMINAL_MAX_SPEED,
  YELLOW_MARGIN_BASE,
  YELLOW_MARGIN_MAX,
  YELLOW_MARGIN_MIN,
  YELLOW_MARGIN_TIME,
  TrafficPlanAction,
  _TrafficStopStyle,
)
from .controller import TrafficControlPhase
from .stop_profile import StopProfileGenerator


class StopPlanMixin:
  """STOP/HOLD/RELEASE trajectory constraints and stop-ownership envelopes."""

  @staticmethod
  def _times(length: int) -> np.ndarray:
    return np.asarray(ModelConstants.T_IDXS[:length], dtype=float)

  @staticmethod
  def _padded_jerks(accels: np.ndarray, times: np.ndarray, output_length: int) -> np.ndarray:
    if len(accels) < 2:
      return np.zeros(output_length, dtype=float)
    jerks = np.diff(accels) / np.maximum(np.diff(times), 1e-3)
    return np.pad(jerks, (0, max(0, output_length - len(jerks))), mode="edge")[:output_length]

  def _stop_target_accel(self, stop_accels: np.ndarray, times: np.ndarray, *, terminal: bool) -> float:
    actuator_time = self._actuator_delay + TERMINAL_LOOKAHEAD_S
    target = float(np.interp(actuator_time, times, stop_accels))
    if terminal:
      actuator_window = stop_accels[times <= actuator_time]
      if len(actuator_window):
        target = min(target, float(np.min(actuator_window)))
    return target

  @staticmethod
  def _base_stop_style(sm, *, yellow_admission: bool = False) -> _TrafficStopStyle:
    personality = sm["selfdriveState"].personality
    if personality == log.LongitudinalPersonality.relaxed:
      base_brake, base_jerk, decel_margin = 2.2, 0.55, 1.15
    elif personality == log.LongitudinalPersonality.aggressive and not yellow_admission:
      base_brake, base_jerk, decel_margin = 2.8, 1.10, 1.02
    else:
      base_brake, base_jerk, decel_margin = 2.5, 0.80, 1.08
    return _TrafficStopStyle(base_brake, base_jerk, decel_margin)

  @staticmethod
  def _speed_jerk_scale(v_ego: float) -> float:
    return float(np.interp(v_ego * 3.6, [0.0, 30.0, 60.0, 90.0], [0.70, 0.85, 1.10, 1.25]))

  def _traffic_stop_style(self, sm, *, remaining_distance: float, terminal: bool) -> _TrafficStopStyle:
    base = self._base_stop_style(sm)

    v_ego = max(0.0, float(sm["carState"].vEgo))
    effective_distance = max(
      remaining_distance - v_ego * (self._actuator_delay + TERMINAL_LOOKAHEAD_S),
      0.5,
    )
    required_brake = v_ego ** 2 / (2.0 * effective_distance)
    comfort_brake = float(np.clip(
      max(base.comfort_brake, required_brake * base.decel_margin),
      base.comfort_brake,
      MAX_TRAFFIC_STOP_BRAKE,
    ))
    # At higher approach speeds, begin changing acceleration more decisively.
    # Personality still shapes the ramp: relaxed is gentler, aggressive reacts
    # faster. Terminal catch keeps a safety floor independent of preference.
    jerk_limit = base.jerk_limit * self._speed_jerk_scale(v_ego)
    decel_margin = base.decel_margin
    if terminal:
      comfort_brake = MAX_TRAFFIC_STOP_BRAKE
      jerk_limit = max(jerk_limit, 1.0)
      decel_margin = max(decel_margin, 1.10)
    return _TrafficStopStyle(comfort_brake, jerk_limit, decel_margin)

  def _traffic_activation_distance(self, sm, *, yellow_admission: bool = False) -> float:
    """Gate ownership with the stop executor's delay, jerk, and brake limits."""
    style = self._base_stop_style(sm, yellow_admission=yellow_admission)
    raw_v_ego = float(sm["carState"].vEgo)
    raw_a_ego = float(sm["carState"].aEgo)
    if not math.isfinite(raw_v_ego) or not math.isfinite(raw_a_ego):
      return 200.0
    v_ego = max(0.0, raw_v_ego)
    braking_distance = StopProfileGenerator.required_stop_distance(
      v_ego=v_ego, a_ego=raw_a_ego,
      actuator_delay=self._actuator_delay + 0.2,
      max_brake=style.comfort_brake,
      jerk_limit=style.jerk_limit * self._speed_jerk_scale(v_ego),
    )
    # Reserve enough distance for 2 Hz signal cadence, one confirmation frame,
    # and style-preserving control convergence before the physical stop model
    # reaches its nominal boundary.
    return float(np.clip(braking_distance + 26.0, 20.0, 200.0))

  def _traffic_stop_feasible(self, sm, remaining_distance: float, phase: TrafficControlPhase) -> bool:
    raw_v_ego = float(sm["carState"].vEgo)
    a_ego = float(sm["carState"].aEgo)
    if not all(math.isfinite(value) for value in (raw_v_ego, a_ego, remaining_distance)):
      return False
    v_ego = max(0.0, raw_v_ego)
    if phase in (TrafficControlPhase.yellowStop, TrafficControlPhase.flashingGreenStop):
      # Yellow and flashing GREEN are advance warnings: STOP must fit the
      # comfortable envelope. Aggressive admission is capped at Standard so
      # a late warning cannot introduce a harsh stop.
      style = self._base_stop_style(sm, yellow_admission=True)
      max_brake = style.comfort_brake
      jerk_limit = style.jerk_limit * self._speed_jerk_scale(v_ego)
      uncertainty_margin = float(np.clip(
        YELLOW_MARGIN_BASE + YELLOW_MARGIN_TIME * v_ego,
        YELLOW_MARGIN_MIN,
        YELLOW_MARGIN_MAX,
      ))
    else:
      max_brake = MAX_TRAFFIC_STOP_BRAKE
      jerk_limit = 1.1
      uncertainty_margin = 0.0
    required_distance = StopProfileGenerator.required_stop_distance(
      v_ego=v_ego, a_ego=a_ego,
      actuator_delay=self._actuator_delay + TERMINAL_LOOKAHEAD_S,
      max_brake=max_brake, jerk_limit=jerk_limit,
    )
    return remaining_distance >= required_distance + uncertainty_margin

  def _apply_stop_constraint(self, plan, sm, *, remaining_distance: float,
                             hold: bool, terminal: bool) -> float:
    base_speeds = np.asarray(plan.speeds, dtype=float)
    base_accels = np.asarray(plan.accels, dtype=float)
    times = self._times(len(base_speeds))
    v_ego = float(sm["carState"].vEgo)
    style = self._traffic_stop_style(sm, remaining_distance=remaining_distance, terminal=terminal)
    stop_speeds, stop_accels, _ = self._profile.build_stop(
      v_ego=v_ego,
      a_ego=float(sm["carState"].aEgo),
      remaining_distance=remaining_distance,
      times=times,
      hold=hold,
      comfort_brake=style.comfort_brake,
      jerk_limit=style.jerk_limit,
      decel_margin=style.decel_margin,
    )
    final_speeds = np.minimum(base_speeds, stop_speeds)
    final_accels = np.minimum(base_accels, stop_accels)
    traffic_a_target = self._stop_target_accel(stop_accels, times, terminal=terminal)
    final_a_target = min(float(plan.aTarget), traffic_a_target)

    plan.speeds = final_speeds.tolist()
    plan.accels = final_accels.tolist()
    plan.jerks = self._padded_jerks(final_accels, times, len(plan.jerks)).tolist()
    plan.aTarget = final_a_target
    plan.shouldStop = bool(plan.shouldStop or hold)
    plan.allowThrottle = bool(plan.allowThrottle and not (hold or terminal))
    return traffic_a_target

  def _apply_stop(self, plan, sm, traffic, now_ns: int) -> None:
    phase = TrafficControlPhase(int(traffic.phase))
    hold = bool(phase == TrafficControlPhase.hold or traffic.shouldStop)
    v_ego = float(sm["carState"].vEgo)
    remaining_distance = max(0.0, float(traffic.distanceToStopPoint))
    terminal_distance = (
      v_ego * (self._actuator_delay + TERMINAL_LOOKAHEAD_S)
      + v_ego ** 2 / (2.0 * self._profile.comfort_brake)
    )
    terminal_stop = bool(
      v_ego > 0.01
      and (
        remaining_distance <= 0.01
        or (v_ego <= TERMINAL_MAX_SPEED and remaining_distance <= terminal_distance)
      )
    )
    traffic_a_target = self._apply_stop_constraint(
      plan, sm,
      remaining_distance=remaining_distance,
      hold=hold,
      terminal=hold or terminal_stop,
    )

    if hold or terminal_stop:
      self._held_event_id = int(traffic.eventId)
      self._held_session_id = int(traffic.stopSessionId)
      self._active_start_session_id = 0
      self._completed_start_session_id = 0
      self._start_started_ns = 0
      self._hold_latched = True
      self._hold_latched_should_stop = self._hold_latched_should_stop or hold
    self._was_stopping = True
    self._owned_stop_session_id = int(traffic.stopSessionId)
    self.diagnostics.action = TrafficPlanAction.hold if hold else TrafficPlanAction.stop
    self.diagnostics.applied = True
    self.diagnostics.traffic_a_target = traffic_a_target
    self.diagnostics.terminal_catch_active = bool(terminal_stop or (hold and v_ego > 0.01))

  def _apply_latched_hold(self, plan, sm) -> None:
    v_ego = float(sm["carState"].vEgo)
    should_stop = self._hold_latched_should_stop or v_ego <= 0.3
    traffic_a_target = self._apply_stop_constraint(
      plan, sm,
      remaining_distance=0.0,
      hold=should_stop,
      terminal=True,
    )
    self._hold_latched_should_stop = should_stop
    self.diagnostics.action = TrafficPlanAction.hold
    self.diagnostics.applied = True
    self.diagnostics.event_id = self._held_event_id
    self.diagnostics.traffic_a_target = traffic_a_target
    self.diagnostics.terminal_catch_active = v_ego > 0.01

  def _apply_invalid_motion_fallback(self, plan) -> None:
    holding = self._hold_latched
    owned_stop = bool(holding or self._armed_stop_session_id != 0 or self._was_stopping)
    self._profile.reset()
    if not owned_stop:
      return
    # Motion geometry is unusable, so do not synthesize a trajectory. Preserve
    # the last owned STOP's minimum current-control contract instead: never add
    # throttle, never turn a known standstill HOLD into a resume, and never let
    # Traffic itself introduce a positive acceleration.
    plan.aTarget = min(float(plan.aTarget), 0.0)
    if holding and self._hold_latched_should_stop:
      plan.shouldStop = True
    plan.allowThrottle = False
    self.diagnostics.action = TrafficPlanAction.hold if holding else TrafficPlanAction.stop
    self.diagnostics.traffic_a_target = 0.0

  def _apply_release(self, plan, sm) -> None:
    if not self._was_stopping:
      self._profile.reset()
      return
    base_speeds = np.asarray(plan.speeds, dtype=float)
    base_accels = np.asarray(plan.accels, dtype=float)
    times = self._times(len(base_speeds))
    release_speeds, release_accels, _ = self._profile.build_release(
      v_ego=float(sm["carState"].vEgo), base_accel=float(plan.aTarget), times=times,
    )
    final_speeds = np.minimum(base_speeds, release_speeds)
    final_accels = np.minimum(base_accels, release_accels)
    release_a_target = float(np.interp(self._actuator_delay + 0.05, times, release_accels))
    final_a_target = min(float(plan.aTarget), release_a_target)
    constrained = bool(
      final_a_target < float(plan.aTarget) - 1e-3
      or np.any(final_speeds < base_speeds - 1e-3)
      or np.any(final_accels < base_accels - 1e-3)
    )
    if not constrained:
      self._was_stopping = False
      self._profile.reset()
      return
    plan.speeds = final_speeds.tolist()
    plan.accels = final_accels.tolist()
    plan.jerks = self._padded_jerks(final_accels, times, len(plan.jerks)).tolist()
    plan.aTarget = final_a_target
    self.diagnostics.action = TrafficPlanAction.release
    self.diagnostics.applied = True
    self.diagnostics.traffic_a_target = release_a_target
