from __future__ import annotations

import numpy as np

from .tesla_observer import (
  TRAFFIC_CONTROL_STALE_NS,
  TeslaTrafficControlObservation,
)
from .controller_types import STOP_EVIDENCE_LOSS_GRACE_S, TrafficControlPhase


class ControllerTrackingMixin:
  """Stop-station geometry, stop/release state, flash-pattern and candidate confirmation."""

  def _distance_tolerance(self, a: float, b: float) -> float:
    return max(self.config.candidate_distance_tolerance,
               self.config.candidate_distance_tolerance_ratio * max(a, b))

  def _same_track(self, observation: TeslaTrafficControlObservation) -> bool:
    if self.last_raw_distance is None:
      return True
    expected = max(0.0, self.last_raw_distance - (self.ego_station - self.last_distance_ego_station))
    innovation = observation.distance - expected
    self.last_distance_innovation = innovation
    return bool(observation.source_bus == self.source_bus and
                abs(innovation) <= self._distance_tolerance(observation.distance, expected))

  def _update_stop_station(self, observation: TeslaTrafficControlObservation) -> None:
    self.can_remaining = max(0.0, observation.distance - self.stop_reference)
    sample = self.ego_station + self.can_remaining
    if self.stop_station is None:
      self.stop_station = sample
      self.remaining_distance = self.can_remaining
    else:
      predicted = max(0.0, self.stop_station - self.ego_station)
      innovation = self.can_remaining - predicted
      self.last_distance_innovation = innovation
      gain = float(np.interp(self.can_remaining, [0.0, 20.0, 50.0, 200.0], [0.90, 0.80, 0.55, 0.30]))
      ego_travel = max(0.0, self.ego_station - self.last_distance_ego_station)
      # Near the line, the roughly 2 Hz CAN cadence leaves only a handful of
      # samples to converge. Preserve the broader replacement slew limit, but
      # allow a trusted final-approach sample to correct an early stop station.
      minimum_correction = 2.0 if self.can_remaining <= 20.0 else 1.0
      max_correction = max(minimum_correction, 0.8 * ego_travel + 0.5)
      correction = float(np.clip(gain * innovation, -max_correction, max_correction))
      self.remaining_distance = max(0.0, predicted + correction)
      self.stop_station = self.ego_station + self.remaining_distance
    self.remaining_distance = max(0.0, (self.stop_station or self.ego_station) - self.ego_station)

  def _hold_distance_consistent(self, *, evidence_lost: bool = False) -> bool:
    # During an evidence gap can_remaining is deliberately frozen. The owned
    # absolute stop station still advances with ego motion and is the only
    # meaningful terminal geometry once the vehicle reaches it.
    return bool(
      self.remaining_distance <= 1.5
      and (evidence_lost or self.can_remaining <= 2.0)
    )

  def _start_stop(self, observation: TeslaTrafficControlObservation, v_ego: float,
                  phase: TrafficControlPhase, reason: str, *, preserve_session: bool = False) -> None:
    self.event_seq += 1
    self.event_id = self.event_seq
    new_session = not preserve_session or self.stop_session_id == 0
    if new_session:
      self.stop_session_seq += 1
      self.stop_session_id = self.stop_session_seq
      self.yellow_latched = phase == TrafficControlPhase.yellowStop
      self.flash_latched = phase == TrafficControlPhase.flashingGreenStop
      self._clear_flash_candidate()
      self.stable_green_since_ns = 0
      self.green_count = 0
      self.pending_distance = 0.0
      self.pending_ego_station = self.ego_station
      self.pending_color = 0
      self._clear_pending_replacement()
      self.release_since_ns = None
      self.release_red_preserve_session = None
    self.stop_evidence_lost_since_ns = 0
    self.stop_reference = self.config.default_stop_reference
    # A stop session is also the ownership boundary for its geometry. Tesla can
    # recalculate the current control-point distance when its color/track
    # changes, so a new session must never inherit a station tracked while
    # GREEN or owned by an earlier stop session.
    if new_session or self.stop_station is None:
      self.stop_station = None
      self.remaining_distance = 0.0
      self.last_distance_innovation = 0.0
    self._update_stop_station(observation)
    required = v_ego ** 2 / (2.0 * max(self.remaining_distance, 0.5))
    self.phase = (TrafficControlPhase.braking if required >= 0.5 else TrafficControlPhase.approachRed) \
      if phase == TrafficControlPhase.approachRed else phase
    self._mark_transition(reason)

  def _set_release(self, now_ns: int, reason: str = "green_release") -> None:
    self.phase = TrafficControlPhase.release
    self.release_since_ns = now_ns
    # GREEN may release and later flicker back to the same event. A signal-loss
    # release is different: motion can resume while evidence is absent, so a
    # recovered RED must own a fresh session and repeat stop feasibility.
    self.release_red_preserve_session = False if reason == "signal_lost_release" else None
    self.stop_evidence_lost_since_ns = 0
    self.candidate_color = 0
    self.candidate_count = 0
    self.candidate_first_ns = 0
    self.candidate_last_ns = 0
    self.candidate_distance = 0.0
    self.candidate_ego_station = self.ego_station
    self._clear_pending_replacement()
    self.remaining_distance = 0.0
    self._mark_transition(reason)

  def _update_stop_evidence_loss(self, now_ns: int) -> None:
    if self.phase == TrafficControlPhase.release:
      self.stop_evidence_lost_since_ns = 0
      if (self.release_since_ns is not None
          and now_ns - self.release_since_ns >= int(self.config.release_s * 1e9)):
        self.reset()
        self.last_update_ns = now_ns
      return
    ordinary_stop = self.phase in (
      TrafficControlPhase.approachRed,
      TrafficControlPhase.braking,
      TrafficControlPhase.yellowStop,
    )
    if not ordinary_stop:
      self.stop_evidence_lost_since_ns = 0
      return
    if self.stop_evidence_lost_since_ns == 0:
      self.stop_evidence_lost_since_ns = now_ns
      return
    if now_ns - self.stop_evidence_lost_since_ns < int(STOP_EVIDENCE_LOSS_GRACE_S * 1e9):
      return
    self._set_release(now_ns, "signal_lost_release")

  def _observe_flash_pattern(self, observation: TeslaTrafficControlObservation) -> bool:
    """Confirm on the second OFF edge after sustained OFF and GREEN.

    Only real CAN frames prove duration. Repeated planner snapshots cannot
    turn one OFF edge into a repeated flash. This detector never owns STOP;
    it emits one confirmation and the existing latched STOP owns its exit.
    """
    # DBC NONE (0) means no recognized light, not an extinguished light. Only
    # explicit OFF (4) alternating with GREEN (2) can prove a flashing signal.
    color = observation.light_state
    frame_ns = observation.frame_mono_time
    flash_eligible = observation.valid_for_control or (color == 4 and observation.control_type == 3)
    if (color not in (2, 4) or not flash_eligible
        or not 0.0 <= observation.distance <= self.config.max_control_distance):
      self._clear_flash_candidate()
      self.stable_green_since_ns = 0
      return False
    if self.flash_latched:
      # Do not repeatedly confirm an owned flash STOP: doing so would bypass
      # its stable-GREEN exit timer on every later blink.
      return False
    if self.phase in (TrafficControlPhase.bypass, TrafficControlPhase.yellowPass):
      self._clear_flash_candidate()
      return False
    if frame_ns <= self.flash_last_frame_ns:
      return False
    if (self.flash_last_frame_ns and frame_ns - self.flash_last_frame_ns > TRAFFIC_CONTROL_STALE_NS
        or not self._same_track(observation)):
      self._clear_flash_candidate()
    if self.flash_anchor_station is not None:
      expected = max(0.0, self.flash_anchor_station - self.ego_station)
      if abs(observation.distance - expected) > self._distance_tolerance(observation.distance, expected):
        # Small per-frame jumps must not cumulatively bridge different control
        # points or a frozen distance while the vehicle is still moving.
        self._clear_flash_candidate()
    confirmed = False
    min_half_ns = int(self.config.flash_min_half_cycle_s * 1e9)
    max_half_ns = int(self.config.flash_interval_max_s * 1e9) - min_half_ns
    duration_ns = frame_ns - self.flash_color_since_ns
    if self.flash_color == 4 and self.first_off_ns and not self.flash_off_confirmed:
      if duration_ns > max_half_ns or (color == 2 and duration_ns < min_half_ns):
        self._clear_flash_candidate()
      elif duration_ns >= min_half_ns:
        self.flash_off_confirmed = True

    if color != self.flash_color:
      if color == 4:
        valid_green = self.flash_color == 2 and duration_ns >= min_half_ns
        period_ns = frame_ns - self.first_off_ns
        valid_period = (
          int(self.config.flash_interval_min_s * 1e9) <= period_ns
          <= int(self.config.flash_interval_max_s * 1e9)
        )
        # A complete GREEN/OFF/GREEN cycle plus the next OFF edge proves
        # repetition. Do not wait for that second OFF to finish or a third
        # pulse: at 2 Hz those extra samples consume the stopping margin.
        confirmed = bool(valid_green and valid_period and self.flash_off_confirmed)
        if not valid_green or (self.first_off_ns and not valid_period):
          self._clear_flash_candidate()
        if valid_green:
          self.first_off_ns = frame_ns
          self.flash_off_confirmed = False
      self.flash_color = color
      self.flash_color_since_ns = frame_ns
    elif self.first_off_ns and duration_ns > max_half_ns:
      self._clear_flash_candidate()
      self.flash_color = color
      self.flash_color_since_ns = frame_ns

    self.flash_last_frame_ns = frame_ns
    if self.flash_anchor_station is None and color == 2:
      self.flash_anchor_station = self.ego_station + observation.distance
    return confirmed

  def _far_stop_candidate(self, observation: TeslaTrafficControlObservation, v_ego: float) -> bool:
    if observation.light_state not in (1, 3):
      return False
    usable_distance = max(observation.distance - self.stop_reference, 0.5)
    required_decel = v_ego ** 2 / (2.0 * usable_distance)
    return required_decel < 0.5

  def _candidate_confirmed(self, observation: TeslaTrafficControlObservation, v_ego: float,
                           count: int, first_ns: int) -> bool:
    if count < 2:
      return False
    if not self._far_stop_candidate(observation, v_ego):
      return True
    return observation.frame_mono_time - first_ns >= int(self.config.far_candidate_confirm_s * 1e9)

  def _update_candidate(self, observation: TeslaTrafficControlObservation, v_ego: float) -> bool:
    expected = max(0.0, self.candidate_distance - (self.ego_station - self.candidate_ego_station))
    same = bool(
      self.candidate_count > 0
      and self.candidate_color == observation.light_state
      and abs(observation.distance - expected) <=
      self._distance_tolerance(observation.distance, expected)
    )
    if same:
      self.candidate_count += 1
    else:
      self.candidate_color = observation.light_state
      self.candidate_count = 1
      self.candidate_first_ns = observation.frame_mono_time
    self.candidate_distance = observation.distance
    self.candidate_ego_station = self.ego_station
    self.candidate_last_ns = observation.frame_mono_time
    return self._candidate_confirmed(
      observation, v_ego, self.candidate_count, self.candidate_first_ns,
    )

  def _pending_replacement_confirmed(self, observation: TeslaTrafficControlObservation, v_ego: float) -> bool:
    expected = max(0.0, self.pending_distance - (self.ego_station - self.pending_ego_station))
    same = bool(
      self.pending_count > 0
      and self.pending_color == observation.light_state
      and abs(observation.distance - expected) <= self._distance_tolerance(observation.distance, expected)
    )
    self.pending_count = self.pending_count + 1 if same else 1
    if not same:
      self.pending_first_ns = observation.frame_mono_time
      self.pending_replacement_farther = self.last_distance_innovation > 0.0
    self.pending_distance = observation.distance
    self.pending_ego_station = self.ego_station
    self.pending_color = observation.light_state
    confirmed = self._candidate_confirmed(
      observation, v_ego, self.pending_count, self.pending_first_ns,
    )
    if not confirmed or not self.pending_replacement_farther:
      return confirmed
    # Moving an owned stop point farther away relaxes braking and can alternate
    # the final plan between STOP and RELEASE. Require an extra real sample and
    # a full second; a nearer correction keeps the faster safety response.
    return bool(
      self.pending_count >= 3
      and observation.frame_mono_time - self.pending_first_ns >=
      int(self.config.farther_replacement_confirm_s * 1e9)
    )
