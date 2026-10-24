from __future__ import annotations

from .tesla_observer import TRAFFIC_CONTROL_STALE_NS, TeslaTrafficControlObservation
from .controller_types import TrafficControlDecision, TrafficControlPhase


class ControllerFrameMixin:
  """State-machine step for one new real CAN frame (second half of update())."""

  def _update_real_frame(self, observation: TeslaTrafficControlObservation, now_ns: int, *,
                         v_ego: float, brake_pressed: bool) -> TrafficControlDecision:
    previous_color = self.last_real_color
    if (self.last_real_frame_ns > 0
        and observation.frame_mono_time - self.last_real_frame_ns > TRAFFIC_CONTROL_STALE_NS):
      self._clear_flash_candidate()
      self.stable_green_since_ns = 0
    self.last_real_frame_ns = observation.frame_mono_time
    self.light_state = observation.light_state
    self.source_bus = observation.source_bus
    self.quality = observation.quality
    flashing_pattern = self._observe_flash_pattern(observation)

    if self.override_reconfirm_required and not self.driver_override_active:
      if observation.light_state in (1, 3) and observation.distance <= self.config.max_control_distance:
        self.override_reconfirm_count += 1
        if self.override_reconfirm_count >= 2:
          self.override_reconfirm_required = False
      else:
        self.override_reconfirm_count = 0

    if observation.distance > self.config.max_control_distance:
      wrapped = bool(self.last_raw_distance is not None and self.last_raw_distance <= 2.0 and observation.distance >= 250.0)
      if observation.distance >= 250.0 and self.phase == TrafficControlPhase.yellowPass:
        self.yellow_latched = None
        self.phase = TrafficControlPhase.passed
      if wrapped:
        self.phase = TrafficControlPhase.passed
        self.stop_session_id = 0
        self.stop_station = None
        self.yellow_latched = None
        self.flash_latched = False
        self._clear_flash_candidate()
        self.stable_green_since_ns = 0
        self.stop_evidence_lost_since_ns = 0
        self.remaining_distance = 0.0
        self._mark_transition("distance_wrap_passed")
      else:
        self._clear_pending_replacement()
        if (v_ego < 0.3 and self.phase in self.ACTIVE_PHASES
            and self._hold_distance_consistent(evidence_lost=bool(self.stop_evidence_lost_since_ns))):
          self.phase = TrafficControlPhase.hold
          self._mark_transition("stationary_hold")
        self._update_stop_evidence_loss(now_ns)
      self.last_real_color = observation.light_state
      return self._decision()

    if observation.light_state not in (0, 4):
      self.stop_evidence_lost_since_ns = 0

    if self.phase == TrafficControlPhase.bypass:
      if self.driver_override_active or v_ego > self.config.max_control_speed:
        self.last_raw_distance = observation.distance
        self.last_distance_ego_station = self.ego_station
        self.last_real_color = observation.light_state
        return self._decision()
      # Gas and over-speed are temporary overrides. Once both end, this frame
      # re-enters normal RED confirmation; the arbitrator feasibility gate
      # rejects a stop that is no longer comfortable.
      self.phase = TrafficControlPhase.off
      self.candidate_count = 0
      self.candidate_first_ns = 0
      self._mark_transition("override_ended")

    if self.phase == TrafficControlPhase.yellowPass:
      predicted = (self.last_raw_distance - (self.ego_station - self.last_distance_ego_station)
                   if self.last_raw_distance is not None else observation.distance)
      if observation.distance <= max(predicted, 0.0) + max(20.0, v_ego):
        # Yellow PASS is a one-time decision for this current-lane event. A
        # later RED cannot reacquire Traffic ownership near the line.
        self.last_raw_distance = observation.distance
        self.last_distance_ego_station = self.ego_station
        self.last_real_color = observation.light_state
        return self._decision()
      # Tesla moved to a farther point without a 255 frame: the passed light
      # no longer owns the yellow PASS.
      self.yellow_latched = None
      self.phase = TrafficControlPhase.off
      self.candidate_count = 0
      self.candidate_first_ns = 0
      self._mark_transition("next_control_point")

    if (self.phase not in (*self.ACTIVE_PHASES, TrafficControlPhase.release)
        and v_ego > self.config.max_control_speed):
      self.candidate_count = 0
      self.candidate_first_ns = 0
      self.phase = TrafficControlPhase.bypass
      self.last_raw_distance = observation.distance
      self.last_distance_ego_station = self.ego_station
      self._mark_transition("speed_above_limit")
      self.last_real_color = observation.light_state
      return self._decision()

    if flashing_pattern:
      if self.stop_reconfirm_required and not self.stop_direction_unknown:
        self.stop_reconfirm_required = False
        self.stop_reconfirm_count = 0
      self._start_stop(observation, v_ego, TrafficControlPhase.flashingGreenStop, "flashing_green_stop")
      if observation.light_state == 2:
        self.stable_green_since_ns = observation.frame_mono_time
      self.last_raw_distance = observation.distance
      self.last_distance_ego_station = self.ego_station
      self.last_real_color = observation.light_state
      return self._decision()

    same_track = self._same_track(observation)
    self.event_continuous = same_track
    if (observation.light_state == 2 and self.phase in self.ACTIVE_PHASES
        and not self.flash_latched):
      # Tesla bus-2 color is authoritative for the current lane. Geometry
      # continuity may protect a stop station from a one-frame distance jump,
      # but it must not permanently veto an ordinary GREEN release. Moving
      # releases on the first real GREEN; standstill still requires two
      # distinct real frames.
      self.green_count = self.green_count + 1 if previous_color == 2 else 1
      self._clear_pending_replacement()
      if (v_ego >= 0.3 or self.green_count >= 2) and not brake_pressed:
        if not same_track:
          self.stop_station = None
        self.can_remaining = max(0.0, observation.distance - self.stop_reference)
        self.last_raw_distance = observation.distance
        self.last_distance_ego_station = self.ego_station
        self.last_real_color = observation.light_state
        self._set_release(now_ns)
      else:
        self.last_real_color = observation.light_state
      return self._decision()

    if observation.light_state in (0, 4) and self.phase in (*self.ACTIVE_PHASES, TrafficControlPhase.release):
      # NONE/OFF are fresh raw data, but neither is STOP geometry nor a GREEN
      # release. Freeze the last confirmed stop point through short OEM color
      # gaps, then smoothly return an ordinary moving STOP to the base planner.
      # A terminal HOLD and a confirmed flashing-green STOP remain latched.
      self._clear_pending_replacement()
      self.stable_green_since_ns = 0
      if (v_ego < 0.3 and self.phase in self.ACTIVE_PHASES
          and self._hold_distance_consistent(evidence_lost=bool(self.stop_evidence_lost_since_ns))):
        self.phase = TrafficControlPhase.hold
        self._mark_transition("stationary_hold")
      self._update_stop_evidence_loss(now_ns)
      self.last_real_color = observation.light_state
      return self._decision()

    if not same_track and self.phase in self.ACTIVE_PHASES:
      self.stable_green_since_ns = 0
      # A single discontinuous tuple cannot replace or release the current
      # lane event. A nearer track confirms in two motion-consistent frames;
      # a farther track needs three frames spanning one second because it
      # relaxes braking. Start a fresh session so geometry and feasibility are
      # both recomputed. HOLD and flashing STOP stay latched and can only be
      # released by their existing GREEN/driver rules.
      replaceable_phase = self.phase in (
        TrafficControlPhase.approachRed,
        TrafficControlPhase.braking,
        TrafficControlPhase.yellowStop,
      )
      replace = bool(
        replaceable_phase and observation.light_state in (1, 3)
        and self._pending_replacement_confirmed(observation, v_ego)
      )
      if not replace:
        if observation.light_state != 2:
          self.green_count = 0
        self.last_real_color = observation.light_state
        return self._decision()
      self.last_raw_distance = observation.distance
      replacement_phase = (TrafficControlPhase.yellowStop if observation.light_state == 3
                           else TrafficControlPhase.approachRed)
      self._start_stop(observation, v_ego, replacement_phase, "candidate_replaced")
      self.event_continuous = True
      self.last_distance_ego_station = self.ego_station
      self.stop_reconfirm_required = False
      self.stop_reconfirm_count = 0
      self._clear_pending_replacement()
      self.last_real_color = observation.light_state
      return self._decision()
    if same_track:
      self._clear_pending_replacement()

    if self.stop_reconfirm_required and not self.stop_direction_unknown:
      if observation.light_state in (1, 3):
        self.stop_reconfirm_count += 1
        if self.stop_reconfirm_count >= 2:
          self.stop_reconfirm_required = False
          self.stop_reconfirm_count = 0
          if self.phase in (
            TrafficControlPhase.approachRed,
            TrafficControlPhase.braking,
            TrafficControlPhase.yellowStop,
          ):
            recovery_phase = (
              TrafficControlPhase.yellowStop if observation.light_state == 3
              else TrafficControlPhase.approachRed
            )
            self._start_stop(observation, v_ego, recovery_phase, "dropout_reconfirmed")
            self.event_continuous = True
            self.last_raw_distance = observation.distance
            self.last_distance_ego_station = self.ego_station
            self.last_real_color = observation.light_state
            return self._decision()
      else:
        self.stop_reconfirm_count = 0

    self._update_stop_station(observation)
    self.last_raw_distance = observation.distance
    self.last_distance_ego_station = self.ego_station

    color = observation.light_state
    confirmed = self._update_candidate(observation, v_ego)

    if self.phase in self.ACTIVE_PHASES:
      # A confirmed red/yellow ends the flashing-green interpretation without
      # ending the stop session. The ordinary stop state can then release on a
      # later stable green instead of keeping flash_latched forever.
      if self.flash_latched and color in (1, 3) and confirmed:
        self.flash_latched = False
      if self.flash_latched:
        if color == 2:
          if self.stable_green_since_ns == 0:
            self.stable_green_since_ns = observation.frame_mono_time
          stable_green_ns = observation.frame_mono_time - self.stable_green_since_ns
          if stable_green_ns >= int(self.config.flash_interval_max_s * 1e9):
            self.flash_latched = False
            self._clear_flash_candidate()
            self._set_release(now_ns)
          else:
            self.phase = (TrafficControlPhase.hold if v_ego < 0.3 and self._hold_distance_consistent()
                          else TrafficControlPhase.flashingGreenStop)
        else:
          self.stable_green_since_ns = 0
          self.phase = (TrafficControlPhase.hold if v_ego < 0.3 and self._hold_distance_consistent()
                        else TrafficControlPhase.flashingGreenStop)
      else:
        self.green_count = 0
        if color == 3:
          self.phase = TrafficControlPhase.yellowStop
        elif color == 1 and self.phase != TrafficControlPhase.hold:
          required = v_ego ** 2 / (2.0 * max(self.remaining_distance, 0.5))
          self.phase = TrafficControlPhase.braking if required >= 0.5 else TrafficControlPhase.approachRed
      if v_ego < 0.3 and self._hold_distance_consistent() and self.phase != TrafficControlPhase.release:
        self.phase = TrafficControlPhase.hold
        self._mark_transition("stationary_hold")
      self.last_real_color = observation.light_state
      return self._decision()

    if self.phase == TrafficControlPhase.release:
      if color == 1:
        if self.release_red_preserve_session is None:
          self.release_red_preserve_session = same_track
        else:
          self.release_red_preserve_session = self.release_red_preserve_session and same_track
        if confirmed:
          self._start_stop(
            observation, v_ego, TrafficControlPhase.approachRed, "red_after_release",
            preserve_session=bool(self.release_red_preserve_session),
          )
          self.release_red_preserve_session = None
      elif self.release_since_ns is not None:
        release_timeout_s = (
          self.config.stationary_release_s if color == 2 and v_ego < 0.3
          else self.config.release_s
        )
        if now_ns - self.release_since_ns >= int(release_timeout_s * 1e9):
          self.reset()
          self.last_update_ns = now_ns
      self.last_real_color = observation.light_state
      return self._decision()

    if color == 1:
      self.phase = TrafficControlPhase.redCandidate
      if confirmed:
        self._start_stop(observation, v_ego, TrafficControlPhase.approachRed, "stop_confirmed")
    elif color == 3:
      required = v_ego ** 2 / (2.0 * max(observation.distance - self.stop_reference, 0.5))
      if self.yellow_latched is None and confirmed:
        if required <= self.config.yellow_stop_decel:
          self.yellow_latched = True
        elif required >= self.config.yellow_pass_decel:
          self.yellow_latched = False
        else:
          self.yellow_latched = required <= self.config.comfort_brake
      if self.yellow_latched is True:
        self._start_stop(observation, v_ego, TrafficControlPhase.yellowStop, "yellow_stop")
      elif self.yellow_latched is False:
        self.phase = TrafficControlPhase.yellowPass
        self._mark_transition("yellow_pass")
      else:
        self.phase = TrafficControlPhase.redCandidate
    elif color == 2:
      self.green_count = self.green_count + 1 if previous_color == 2 else 1
      if self.phase != TrafficControlPhase.greenFlashCandidate and self.green_count >= 2:
        self.phase = TrafficControlPhase.off
        self.yellow_latched = None
        self.flash_latched = False
        self.stable_green_since_ns = 0
    elif color in (0, 4) and self.phase != TrafficControlPhase.greenFlashCandidate:
      self.phase = TrafficControlPhase.off
      self.yellow_latched = None
      self.flash_latched = False
      self.stable_green_since_ns = 0

    self.last_real_color = observation.light_state
    return self._decision()
