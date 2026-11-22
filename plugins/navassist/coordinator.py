from __future__ import annotations

from dataclasses import replace as _dc_replace

from .intent_types import (LaneIntentDirection, ObservedLaneChangeState, NavLanePlan, LaneTopologyInput, LaneVehicleInput, NavTurnPlan, NavLaneIntent)
from .turn_intent import NavTurnSignalCoordinator
from .preparation import LanePreparation


def _absolute_topology(plan: NavLanePlan, topology: LaneTopologyInput) -> LaneTopologyInput:
  # ABS_STEP：绝对车道计划用高德车道数/绝对车道号做健康判断和方向；
  # 邻道只有在可见拓扑明确看到路沿(False)或高德说没有那条车道时才算不存在。
  ego, count = int(plan.absolute_ego_index), int(plan.lane_count)
  def side(visible, exists):
    return False if (visible is False or not exists) else True
  return _dc_replace(topology, visible_lane_count=count, ego_lane_index=ego,
                     left_neighbor_exists=side(topology.left_neighbor_exists, ego > 0),
                     right_neighbor_exists=side(topology.right_neighbor_exists, ego < count - 1))


class NavLaneIntentCoordinator(LanePreparation):
  _abs_start = None   # ABS_STEP：当前候选的起始绝对车道号（非绝对计划为 None）
  _abs_done = None    # ABS_STEP：(event_key, 起始绝对号)，绝对号未更新前不再发下一步
  _abs_other_since_ns = 0   # REPLAN_RESET 11-14：绝对号离开起始号的开始时间
  _abs_left_start = False   # REPLAN_RESET：绝对号已稳定离开过起始号（说明车道号跟上了变道）
  ABS_LEFT_STABLE_NS = 2_000_000_000

  def note_abs_observation(self, ego, lane_change_starting: bool, now_ns: int) -> None:
    """REPLAN_RESET 11-14：每帧由 intent.LaneIntentCoordinator 调用（导航车道信息缺失时也会调用）。

    变道完成后融合车道号经常不跟（日志 21:21、21:28 两次变道后 abs 仍是起始号），旧逻辑对整个机动一直
    “等绝对车道号”(waitingAbsoluteLane)，司机再变回原车道后也不会再提示。
    现在：绝对号稳定(>=2 秒)离开过起始号、之后又回到起始号 = 司机变回去了 -> 清掉，允许重新规划；
    绝对号一直停在起始号（融合没跟上）时仍然等待，避免对同一步重复变道。"""
    if self._abs_done is None or self._phase != "idle":
      return
    if not isinstance(ego, int) or ego < 0:
      return
    if ego != self._abs_done[1]:
      if self._abs_other_since_ns == 0:
        self._abs_other_since_ns = now_ns
      elif now_ns - self._abs_other_since_ns >= self.ABS_LEFT_STABLE_NS:
        self._abs_left_start = True
    else:
      self._abs_other_since_ns = 0
      if self._abs_left_start:
        self._abs_done = None

  def update(self, plan: NavLanePlan, topology: LaneTopologyInput, vehicle: LaneVehicleInput,
             *, now_ns: int, allow_new_lane_change: bool = True) -> NavLaneIntent:
    _abs_mode = bool(plan.valid and getattr(plan, 'absolute_ego_index', None) is not None)
    if _abs_mode:
      topology = _absolute_topology(plan, topology)
    if self._phase in ("signaling", "ready", "observing") and self._candidate is not None:
      _event_key, start_ego, direction, _target_index, _relative_edge = self._candidate
      if vehicle.lane_change_state == ObservedLaneChangeState.starting and vehicle.lane_change_direction == direction:
        # Observe the SP transition before deciding whether a new action may
        # start: reaching the turn window must not cut an action already begun.
        self._phase = "changing"
        self._phase_since_ns = now_ns
        self._expected_lane_index = self._adjacent_target_index(start_ego, direction)
        self._completion_since_ns = 0
    event_key = self._event_key(plan)
    if event_key != self._plan_recovery_count_key:
      self._plan_recovery_count_key = event_key
      self._plan_recovery_count = 0
    # 油门不算接管，照样打灯变道；只有踩刹车才取消。
    vehicle_healthy = bool(
      vehicle.lateral_active and not vehicle.brake_pressed
      and vehicle.speed_mps <= self.MAX_SPEED_MPS
      and (self._phase == "changing" or vehicle.speed_mps >= self.MIN_SPEED_MPS)
    )
    # ABS_ONLY_OK: 视觉看不到车道时，只要规划带了 GPS 绝对车道号，控制链依然可用。
    _absolute_ok = (plan.absolute_ego_index is not None
                    and 0 <= int(plan.absolute_ego_index) < max(int(plan.lane_count), 1))
    topology_healthy = bool(
      (topology.valid_for_control and plan.lane_count == topology.visible_lane_count
       and 0 <= topology.ego_lane_index < topology.visible_lane_count)
      or _absolute_ok
    )
    base_healthy = bool(plan.valid and vehicle_healthy)
    recovery = self._recover_plan_observation(
      plan, topology, vehicle, now_ns=now_ns, vehicle_healthy=vehicle_healthy,
      topology_healthy=topology_healthy, allow_new_lane_change=allow_new_lane_change,
    )
    if recovery is not None:
      return recovery
    relative_direction = self._relative_direction(plan)
    if relative_direction != LaneIntentDirection.none and (not base_healthy or not topology_healthy):
      self._relative_consistency.update(
        (plan.session_id, plan.route_revision, plan.maneuver_event_id),
        direction="left" if relative_direction == LaneIntentDirection.left else "right",
        neighbor_exists=False, observation_valid=False, lane_change_active=False,
        steering_pressed=vehicle.steering_pressed, now_ns=now_ns,
      )
    if not base_healthy:
      if self._phase not in ("idle", "cooldown") and self._candidate is not None:
        return self._abort(self._candidate[0], "health")
      self._reset()
      return self._idle("health")

    # Observation/source waits return before the normal signaling branch.
    # Apply the same overall budget so intermittent recovery cannot hold a
    # preparation lamp indefinitely or obtain a fresh budget on each switch.
    if (self._phase in ("signaling", "ready", "observing") and self._candidate is not None
        and now_ns - self._signal_since_ns > self.SIGNAL_WAIT_TIMEOUT_NS):
      return self._abort(self._candidate[0], "crossingWaitTimeout")

    if self._phase in ("signaling", "ready", "observing") and not allow_new_lane_change:
      self._reset()
      return self._idle("turnApproachHandoff")

    if self._phase == "changing" and self._candidate is not None:
      if now_ns - self._phase_since_ns > self.LANE_CHANGE_TIMEOUT_NS:
        return self._abort(self._candidate[0], "laneChangeTimeout")

    if not topology_healthy:
      if self._phase in ("signaling", "ready", "observing") and self._candidate is not None:
        if self._event_key(plan) != self._candidate[0]:
          return self._abort(self._candidate[0], "routeChanged")
        return self._observe_before_start(now_ns, recovering=False)
      if self._phase == "changing" and self._candidate is not None:
        self._completion_since_ns = 0
        event_key, _start_ego, direction, target_index, _relative_edge = self._candidate
        if self._event_key(plan) != event_key:
          return self._abort(event_key, "routeChanged")
        physical_signal_on = ((vehicle.left_blinker and not vehicle.right_blinker)
                              if direction == LaneIntentDirection.left else
                              (vehicle.right_blinker and not vehicle.left_blinker))
        if not physical_signal_on:
          return self._abort(event_key, "physicalSignalLost")
        if self._topology_invalid_since_ns == 0:
          self._topology_invalid_since_ns = now_ns
        elif now_ns - self._topology_invalid_since_ns > self.TOPOLOGY_TRANSITION_GRACE_NS:
          return self._abort(event_key, "topologyTransitionTimeout")
        return NavLaneIntent(
          signal_requested=True, lane_change_ready=True, direction=direction,
          request_id=self._request_id, target_lane_index=self._expected_lane_index,
          reason=self._plan_reason(plan, "topologyTransition"),
        )
      self._reset()
      return self._idle("health")
    self._topology_invalid_since_ns = 0

    relative_status = None
    if relative_direction != LaneIntentDirection.none:
      relative_neighbor = (topology.left_neighbor_exists if relative_direction == LaneIntentDirection.left
                           else topology.right_neighbor_exists)
      relative_status = self._relative_consistency.update(
        (plan.session_id, plan.route_revision, plan.maneuver_event_id),
        direction="left" if relative_direction == LaneIntentDirection.left else "right",
        neighbor_exists=relative_neighbor,
        observation_valid=topology_healthy,
        lane_change_active=vehicle.lane_change_state in (ObservedLaneChangeState.starting, ObservedLaneChangeState.finishing),
        steering_pressed=vehicle.steering_pressed,
        now_ns=now_ns,
      )

    if self._phase in ("signaling", "ready", "observing") and self._candidate is not None:
      event_key, _ego, direction, _target, _relative = self._candidate
      if self._event_key(plan) != event_key:
        return self._abort(event_key, "routeChanged")
      neighbor = topology.left_neighbor_exists if direction == LaneIntentDirection.left else topology.right_neighbor_exists
      if neighbor is False and not plan.force_fork:
        return self._abort(event_key, "noNeighbor")
      if (neighbor is None and not plan.force_fork) or self._phase == "observing":
        waiting = self._observe_before_start(
          now_ns, recovering=(neighbor is True or plan.force_fork) and not vehicle.steering_pressed,
        )
        if waiting is not None:
          return waiting

    if self._phase == "cooldown":
      if now_ns - self._phase_since_ns < self.COOLDOWN_NS:
        return self._idle("cooldown")
      relative_edge = bool(self._candidate is not None and self._candidate[4])
      if not relative_edge and topology.ego_lane_index != self._expected_lane_index:
        return self._abort(self._candidate[0] if self._candidate is not None else None, "laneChangeNotObserved")
      self._reset()
      return self._idle("laneChangeComplete")

    if self._phase == "changing" and self._candidate is not None:
      event_key, _start_ego, direction, target_index, relative_edge = self._candidate
      if self._event_key(plan) != event_key:
        return self._abort(event_key, "routeChanged")
      if (vehicle.lane_change_state in (ObservedLaneChangeState.pre, ObservedLaneChangeState.starting,
                                        ObservedLaneChangeState.finishing) and
          vehicle.lane_change_direction != direction):
        return self._abort(event_key, "directionMismatch")
      physical_signal_on = ((vehicle.left_blinker and not vehicle.right_blinker)
                            if direction == LaneIntentDirection.left else
                            (vehicle.right_blinker and not vehicle.left_blinker))
      if not physical_signal_on:
        return self._abort(event_key, "physicalSignalLost")
      model_cycle_complete = vehicle.lane_change_state in (
        ObservedLaneChangeState.off, ObservedLaneChangeState.pre,
      )
      if (relative_edge or topology.ego_lane_index == self._expected_lane_index) and model_cycle_complete:
        if self._completion_since_ns == 0:
          self._completion_since_ns = now_ns
        elif now_ns - self._completion_since_ns >= self.LANE_INDEX_STABLE_NS:
          if relative_edge and self._abs_start is None:
            self._relative_consistency.note_lane_change_completed(now_ns)
          if self._abs_start is not None:
            self._abs_done = (event_key, self._abs_start)
            self._abs_other_since_ns = 0
            self._abs_left_start = False
            self._abs_start = None
          self._phase = "cooldown"
          self._phase_since_ns = now_ns
          return self._idle("laneChangeObserved")
      else:
        self._completion_since_ns = 0
      return NavLaneIntent(
        signal_requested=True,
        lane_change_ready=True,
        direction=direction,
        request_id=self._request_id,
        target_lane_index=self._expected_lane_index,
        reason=self._plan_reason(plan, self._phase),
      )

    relative_limit = self._relative_consistency.max_changes
    if plan.relative_change_limit is not None:
      relative_limit = min(relative_limit, plan.relative_change_limit)
    if relative_status is not None and relative_status.completed_changes >= relative_limit:
      self._reset()
      return self._idle(self._plan_reason(plan, "changeLimit"))

    if not allow_new_lane_change:
      self._reset()
      return self._idle("turnApproachHandoff")

    if (_abs_mode and self._phase == "idle" and self._abs_done is not None
        and self._abs_done == (event_key, topology.ego_lane_index)):
      return self._idle("waitingAbsoluteLane")
    target_index = self._target(plan, topology.ego_lane_index)
    if target_index is None:
      self._reset()
      return self._idle("noRecommendedLane")
    direction = relative_direction if relative_direction != LaneIntentDirection.none else self._direction(topology.ego_lane_index, target_index)
    candidate = (event_key, topology.ego_lane_index, direction, target_index, plan.heuristic or _abs_mode)
    if self._phase == "idle":
      self._abs_start = topology.ego_lane_index if _abs_mode else None
    same_preparation = bool(
      self._phase in ("signaling", "ready", "observing") and self._candidate is not None
      and self._candidate[:4] == candidate[:4]
    )
    if same_preparation and self._candidate[4] != candidate[4]:
      # Absolute-lane confirmation may flicker while the same adjacent target
      # remains visible. Preserve the physical request, but never inherit old
      # readiness or relative-observation time across a source transition.
      self._candidate = candidate
      self._crossing_since_ns = 0
      self._phase = "signaling"
      self._phase_since_ns = now_ns
      if relative_direction != LaneIntentDirection.none:
        args = dict(direction="left" if direction == LaneIntentDirection.left else "right",
                    neighbor_exists=(topology.left_neighbor_exists if direction == LaneIntentDirection.left
                                     else topology.right_neighbor_exists), lane_change_active=False,
                    steering_pressed=vehicle.steering_pressed, now_ns=now_ns)
        self._relative_consistency.update(event_key, observation_valid=False, **args)
        relative_status = self._relative_consistency.update(event_key, observation_valid=True, **args)
    relative_cycle_active = vehicle.lane_change_state in (ObservedLaneChangeState.starting, ObservedLaneChangeState.finishing)
    if (relative_status is not None and not relative_status.ready and not plan.force_fork
        and self._phase != "changing" and not relative_cycle_active):
      if (same_preparation and relative_status.reason in ("stabilizingNeighbor", "stabilizingNewNeighbor")
          and not vehicle.steering_pressed):
        self._crossing_since_ns = 0
        return NavLaneIntent(
          signal_requested=True, direction=direction, request_id=self._request_id,
          target_lane_index=self._adjacent_target_index(topology.ego_lane_index, direction),
          reason="planSourceStabilizing",
        )
      self._blocked_key = None
      self._reset()
      return self._idle(self._plan_reason(plan, relative_status.reason))
    if direction == LaneIntentDirection.none:
      self._blocked_key = None
      self._reset()
      return self._idle("alreadyInRecommendedLane")

    event_key = self._event_key(plan)
    if self._blocked_key == event_key:
      return self._idle("blockedEvent")

    neighbor_exists = topology.left_neighbor_exists if direction == LaneIntentDirection.left else topology.right_neighbor_exists
    if neighbor_exists is None and not plan.force_fork:
      # 邻道未知不再阻断：先把灯打出来，让车端有机会执行；已在路沿的情况规划层不会给出目标。
      neighbor_exists = True
    if not neighbor_exists and not plan.force_fork:
      return self._abort(event_key, "noNeighbor")

    if self._phase == "idle":
      if candidate != self._candidate:
        self._candidate = candidate
        self._candidate_since_ns = now_ns
        if not plan.force_fork:
          return self._idle(self._plan_reason(plan, "stabilizingLaneAlignment"))
      if not plan.force_fork and now_ns - self._candidate_since_ns < self.MISMATCH_STABLE_NS:
        return self._idle(self._plan_reason(plan, "stabilizingLaneAlignment"))
      # A stable navigation target requests the lamp/preparation independently
      # of permission to cross. Solid paint and blindspots still gate readiness
      # below, and DesireHelper independently vetoes actual lateral initiation.
      # Neighbor existence, topology/vehicle health and the bounded signal wait
      # remain prerequisites; a lamp never means that the target lane is clear.
      self._phase = "signaling"
      self._phase_since_ns = now_ns
      self._signal_since_ns = now_ns
      self._crossing_since_ns = 0
      self._request_id += 1

    if self._candidate != candidate and self._phase != "cooldown":
      self._reset()
      self._candidate = candidate
      self._candidate_since_ns = now_ns
      return self._idle("routeChanged")

    if self._phase in ("ready", "changing") and now_ns - self._phase_since_ns > self.LANE_CHANGE_TIMEOUT_NS:
      return self._abort(event_key, "laneChangeTimeout")

    if vehicle.lane_change_state in (ObservedLaneChangeState.starting, ObservedLaneChangeState.finishing):
      if vehicle.lane_change_direction != direction:
        return self._abort(event_key, "directionMismatch")
      if vehicle.lane_change_state == ObservedLaneChangeState.starting:
        self._phase = "changing"
        self._phase_since_ns = now_ns
        self._expected_lane_index = self._adjacent_target_index(topology.ego_lane_index, direction)
        self._completion_since_ns = 0
      else:
        # DesireHelper implementations differ on whether finishing is emitted.
        # Absolute plans still require a stable one-lane index change. Relative
        # edge plans use the completed SP lane-change cycle because modelV2 can
        # recenter the same local ego index after crossing a boundary.
        self._phase = "changing"

    crossing_allowed = topology.left_crossing_allowed if direction == LaneIntentDirection.left else topology.right_crossing_allowed
    blindspot = vehicle.left_blindspot if direction == LaneIntentDirection.left else vehicle.right_blindspot
    physical_signal_on = ((vehicle.left_blinker and not vehicle.right_blinker)
                          if direction == LaneIntentDirection.left else
                          (vehicle.right_blinker and not vehicle.left_blinker))
    if self._phase == "signaling":
      if now_ns - self._signal_since_ns > self.SIGNAL_WAIT_TIMEOUT_NS:
        return self._abort(event_key, "crossingWaitTimeout")
      if crossing_allowed and not blindspot and physical_signal_on:
        if self._crossing_since_ns == 0:
          self._crossing_since_ns = now_ns
        if now_ns - self._crossing_since_ns >= self.CROSSING_STABLE_NS:
          self._phase = "ready"
          self._phase_since_ns = now_ns
      else:
        self._crossing_since_ns = 0
    elif self._phase == "ready" and (not crossing_allowed or blindspot or not physical_signal_on):
      self._phase = "signaling"
      self._crossing_since_ns = 0

    ready = self._phase in ("ready", "changing")
    reason = self._phase
    if self._phase == "signaling":
      if not crossing_allowed:
        reason = "waitingCrossing"
      elif blindspot:
        reason = "waitingBlindspot"
    return NavLaneIntent(
      signal_requested=True,
      lane_change_ready=ready,
      direction=direction,
      request_id=self._request_id,
      target_lane_index=self._adjacent_target_index(topology.ego_lane_index, direction),
      reason=self._plan_reason(plan, reason),
    )

