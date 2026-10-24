from __future__ import annotations

from .tesla_observer import (
  TRAFFIC_CONTROL_STALE_NS,
  TeslaTrafficControlObservation,
)
from .controller_types import (  # noqa: F401  re-exported public names
  STOP_EVIDENCE_LOSS_GRACE_S,
  TrafficControlConfig,
  TrafficControlDecision,
  TrafficControlMode,
  TrafficControlPhase,
)
from .controller_frame import ControllerFrameMixin
from .controller_tracking import ControllerTrackingMixin


class TeslaTrafficControlController(ControllerTrackingMixin, ControllerFrameMixin):
  """CAN-color traffic-light state machine with a CP-style latched stop point."""

  ACTIVE_PHASES = (
    TrafficControlPhase.approachRed,
    TrafficControlPhase.braking,
    TrafficControlPhase.hold,
    TrafficControlPhase.flashingGreenStop,
    TrafficControlPhase.yellowStop,
  )

  def __init__(self, config: TrafficControlConfig | None = None) -> None:
    self.config = config or TrafficControlConfig()
    self.transition_seq = 0
    self.transition_reason = ""
    self.event_seq = 0
    self.event_id = 0
    self.stop_session_seq = 0
    self.stop_session_id = 0
    self.phase = TrafficControlPhase.off
    self.last_update_ns: int | None = None
    self.last_real_frame_ns = 0
    self.last_real_color = 0
    self.last_raw_distance: float | None = None
    self.last_distance_ego_station = 0.0
    self.ego_station = 0.0
    self.stop_station: float | None = None
    self.remaining_distance = 0.0
    self.stop_reference = self.config.default_stop_reference
    self.light_state = 0
    self.source_bus = 0
    self.quality = 0
    self.event_continuous = False
    self.candidate_color = 0
    self.candidate_count = 0
    self.candidate_first_ns = 0
    self.candidate_last_ns = 0
    self.candidate_distance = 0.0
    self.candidate_ego_station = 0.0
    self.pending_distance = 0.0
    self.pending_ego_station = 0.0
    self.pending_color = 0
    self.pending_count = 0
    self.pending_first_ns = 0
    self.pending_replacement_farther = False
    self.green_count = 0
    self._clear_flash_candidate()
    self.flash_latched = False
    self.stable_green_since_ns = 0
    self.yellow_latched: bool | None = None
    self.release_since_ns: int | None = None
    self.release_red_preserve_session: bool | None = None
    self.driver_override_until_ns = 0
    self.driver_override_active = False
    self.override_reconfirm_required = False
    self.override_reconfirm_count = 0
    self.direction_unknown = False
    self.stop_direction_unknown = False
    self.stop_reconfirm_required = False
    self.stop_reconfirm_count = 0
    self.raw_observation_fresh = False
    self.raw_stale_since_ns: int | None = None
    self.stop_evidence_lost_since_ns = 0
    self.can_remaining = 0.0
    self.last_distance_innovation = 0.0

  def _mark_transition(self, reason: str) -> None:
    self.transition_seq += 1
    self.transition_reason = reason

  def _clear_pending_replacement(self) -> None:
    self.pending_count = 0
    self.pending_first_ns = 0
    self.pending_replacement_farther = False

  def _clear_flash_candidate(self) -> None:
    self.first_off_ns = 0
    self.flash_color = -1
    self.flash_color_since_ns = 0
    self.flash_last_frame_ns = 0
    self.flash_off_confirmed = False
    self.flash_anchor_station: float | None = None

  def set_config(self, config: TrafficControlConfig) -> None:
    previous_mode = self.config.mode
    self.config = config
    if config.mode == TrafficControlMode.off and previous_mode != TrafficControlMode.off:
      self.reset()
    elif self.phase == TrafficControlPhase.off:
      self.stop_reference = config.default_stop_reference

  def reset(self) -> None:
    self.phase = TrafficControlPhase.off
    self.event_id = 0
    self.stop_session_id = 0
    self.last_real_frame_ns = 0
    self.last_real_color = 0
    self.last_raw_distance = None
    self.last_distance_ego_station = self.ego_station
    self.stop_station = None
    self.remaining_distance = 0.0
    self.stop_reference = self.config.default_stop_reference
    self.light_state = 0
    self.source_bus = 0
    self.quality = 0
    self.event_continuous = False
    self.candidate_color = 0
    self.candidate_count = 0
    self.candidate_first_ns = 0
    self.candidate_last_ns = 0
    self.candidate_distance = 0.0
    self.candidate_ego_station = self.ego_station
    self.pending_distance = 0.0
    self.pending_ego_station = self.ego_station
    self.pending_color = 0
    self.pending_count = 0
    self.pending_first_ns = 0
    self.pending_replacement_farther = False
    self.green_count = 0
    self._clear_flash_candidate()
    self.flash_latched = False
    self.stable_green_since_ns = 0
    self.yellow_latched = None
    self.release_since_ns = None
    self.release_red_preserve_session = None
    self.last_distance_innovation = 0.0
    self.driver_override_until_ns = 0
    self.driver_override_active = False
    self.override_reconfirm_required = False
    self.override_reconfirm_count = 0
    self.direction_unknown = False
    self.stop_direction_unknown = False
    self.stop_reconfirm_required = False
    self.stop_reconfirm_count = 0
    self.raw_observation_fresh = False
    self.raw_stale_since_ns = None
    self.stop_evidence_lost_since_ns = 0
    self.can_remaining = 0.0
    self.last_update_ns = None

  def _decision(self) -> TrafficControlDecision:
    active = self.phase in self.ACTIVE_PHASES or self.phase == TrafficControlPhase.release
    apply_constraint = (self.config.mode in (TrafficControlMode.stopOnly, TrafficControlMode.stopGo) and active
                        and not self.driver_override_active and not self.override_reconfirm_required)
    stop_safety_allowed = bool(apply_constraint and not self.stop_reconfirm_required)
    stop_fresh_enough = self.raw_observation_fresh or self.phase == TrafficControlPhase.hold
    return TrafficControlDecision(
      mode=self.config.mode,
      phase=self.phase,
      active=active,
      apply_constraint=apply_constraint,
      shadow=self.config.mode == TrafficControlMode.shadow and active,
      should_stop=self.phase == TrafficControlPhase.hold,
      remaining_distance=max(0.0, self.remaining_distance),
      stop_reference=self.stop_reference,
      light_state=self.light_state,
      source_bus=self.source_bus,
      quality=self.quality,
      stop_session_id=self.stop_session_id,
      driver_override_active=self.driver_override_active,
      direction_unknown=self.direction_unknown,
      can_remaining=self.can_remaining,
      station_innovation=self.last_distance_innovation,
      stop_control_allowed=bool(stop_safety_allowed and stop_fresh_enough),
      stop_safety_allowed=stop_safety_allowed,
      raw_observation_fresh=self.raw_observation_fresh,
      stop_direction_unknown=self.stop_direction_unknown,
    )

  def update(self, observation: TeslaTrafficControlObservation, now_ns: int, *, v_ego: float, a_ego: float,
             enabled: bool, long_active: bool, gas_pressed: bool,
             brake_pressed: bool, turn_signal_active: bool,
             stop_direction_unknown: bool | None = None) -> TrafficControlDecision:
    del a_ego
    dt = 0.0 if self.last_update_ns is None else max(0.0, min((now_ns - self.last_update_ns) / 1e9, 0.5))
    self.last_update_ns = now_ns
    self.ego_station += max(0.0, v_ego) * dt
    if self.stop_station is not None:
      self.remaining_distance = max(0.0, self.stop_station - self.ego_station)
    self.event_continuous = False

    if self.config.mode == TrafficControlMode.off:
      self.reset()
      return self._decision()
    was_override_active = self.driver_override_active
    if gas_pressed:
      self.driver_override_until_ns = now_ns + int(self.config.driver_override_cooldown_s * 1e9)
    self.driver_override_active = gas_pressed or now_ns < self.driver_override_until_ns
    if self.driver_override_active:
      self.override_reconfirm_required = True
      self.override_reconfirm_count = 0
    elif was_override_active:
      self.override_reconfirm_required = True
      self.override_reconfirm_count = 0
    # Tesla 0x25D already represents the signal selected for the current lane.
    # Turn indicators and model manoeuvre intent remain diagnostic inputs only;
    # they must not veto an authoritative current-lane STOP or RELEASE.
    del turn_signal_active, stop_direction_unknown
    self.direction_unknown = False
    self.stop_direction_unknown = False
    if gas_pressed:
      self.phase = TrafficControlPhase.bypass
      self.stop_session_id = 0
      self._mark_transition("driver_bypass")
    self.raw_observation_fresh = observation.available
    if self.raw_observation_fresh:
      stale_gap = bool(
        self.raw_stale_since_ns is not None
        and now_ns - self.raw_stale_since_ns >= int(self.config.critical_observation_dropout_s * 1e9)
      )
      real_frame_gap = bool(
        self.last_real_frame_ns > 0 and observation.frame_mono_time > self.last_real_frame_ns
        and observation.frame_mono_time - self.last_real_frame_ns >= int(self.config.critical_observation_dropout_s * 1e9)
      )
      long_dropout = stale_gap or real_frame_gap
      if long_dropout:
        # Confirmation counters describe consecutive real CAN evidence and
        # cannot span a multi-second transport gap.
        self.green_count = 0
        self.stable_green_since_ns = 0
        self.candidate_count = 0
        self.candidate_first_ns = 0
        self.candidate_last_ns = 0
        self._clear_pending_replacement()
        if not self.flash_latched:
          self._clear_flash_candidate()
      if long_dropout and self.phase in self.ACTIVE_PHASES:
        self.stop_reconfirm_required = True
        self.stop_reconfirm_count = 0
      if long_dropout and self.phase == TrafficControlPhase.release:
        # A release is only valid while the confirming green observation is
        # continuous. Do not let one recovery frame revive an old GO session.
        self.reset()
        self.last_update_ns = now_ns
        return self._decision()
      self.raw_stale_since_ns = None
    elif self.raw_stale_since_ns is None:
      self.raw_stale_since_ns = self.last_real_frame_ns if self.last_real_frame_ns > 0 else now_ns
    if not enabled or (self.config.mode in (TrafficControlMode.stopOnly, TrafficControlMode.stopGo) and not long_active):
      self.reset()
      return self._decision()
    new_frame = bool(observation.available and observation.frame_mono_time > 0 and
                     observation.frame_mono_time != self.last_real_frame_ns and
                     observation.source_bus == 2 and observation.dlc >= 6 and
                     observation.control_type == 3 and observation.light_state in (0, 1, 2, 3, 4))
    if not new_frame:
      unsupported_raw_frame = bool(
        observation.available and observation.frame_mono_time > 0
        and observation.frame_mono_time != self.last_real_frame_ns
        and observation.source_bus == 2 and observation.dlc >= 6
        and (observation.control_type != 3 or observation.light_state not in (0, 1, 2, 3, 4))
      )
      if unsupported_raw_frame:
        # A fresh tuple with unsupported semantics is evidence loss, not a CAN
        # transport dropout and never valid geometry for an owned moving STOP.
        self._clear_pending_replacement()
        self._clear_flash_candidate()
        self.stable_green_since_ns = 0
        self._update_stop_evidence_loss(now_ns)
      if (not observation.available and self.last_real_frame_ns > 0
          and now_ns - self.last_real_frame_ns > TRAFFIC_CONTROL_STALE_NS):
        self._clear_flash_candidate()
        self.stable_green_since_ns = 0
      if self.phase in (TrafficControlPhase.redCandidate, TrafficControlPhase.greenFlashCandidate):
        if self.candidate_last_ns and now_ns - self.candidate_last_ns > int(self.config.candidate_dropout_s * 1e9):
          self.phase = TrafficControlPhase.off
          self.candidate_count = 0
          self.candidate_first_ns = 0
      transport_evidence_lost = bool(
        not observation.available and self.raw_stale_since_ns is not None
      )
      if (v_ego < 0.3 and self.phase in self.ACTIVE_PHASES
          and self._hold_distance_consistent(
            evidence_lost=bool(self.stop_evidence_lost_since_ns) or transport_evidence_lost,
          )):
        self.phase = TrafficControlPhase.hold
      if self.stop_evidence_lost_since_ns:
        self._update_stop_evidence_loss(now_ns)
      return self._decision()

    return self._update_real_frame(observation, now_ns, v_ego=v_ego, brake_pressed=brake_pressed)
