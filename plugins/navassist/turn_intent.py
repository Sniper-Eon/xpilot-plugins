from __future__ import annotations

from .intent_types import (LaneIntentDirection, ObservedLaneChangeState, NavLanePlan, LaneTopologyInput, LaneVehicleInput, NavTurnPlan, NavLaneIntent)


TURN_HOLD_SPEED_MPS = 8.0
ARRIVE_DISTANCE_M = 5.0        # 到达路口判定（米）
ARRIVE_HOLD_NS = 0             # 到达路口立即放手（转弯一般 2-3 秒完成）
POST_TURN_SUPPRESS_NS = 3_000_000_000  # 通过路口后暂不再打灯（缩短，避免误伤连续转弯）


class NavTurnSignalCoordinator:
  """Requests a physical lamp for a route turn without authorizing a lane change."""

  SIGNAL_TIMEOUT_NS = 60_000_000_000
  PLAN_GAP_GRACE_NS = 1_500_000_000
  LOOKAHEAD_TIME_S = 8.0
  # Forks, exits and merges should warn as soon as they are announced, but only from a sane distance.
  # 真正的路口转弯（不含并道/匝道）；市区低速时只提前 60 m 打灯。
  TURN_MANEUVERS = frozenset((
    "turnLeft", "turnRight", "sharpLeft", "sharpRight", "uTurnLeft", "uTurnRight",
  ))
  IMMEDIATE_ARM_MANEUVERS = frozenset((
    "slightLeft", "slightRight", "keepLeft", "keepRight",
    "exitLeft", "exitRight", "rampLeft", "rampRight", "mergeLeft", "mergeRight",
  ))
  IMMEDIATE_ARM_MAX_M = {
    "slightLeft": 600.0, "slightRight": 600.0, "keepLeft": 600.0, "keepRight": 600.0,
    "exitLeft": 800.0, "exitRight": 800.0, "rampLeft": 800.0, "rampRight": 800.0,
    "mergeLeft": 800.0, "mergeRight": 800.0,
  }
  MIN_LOOKAHEAD_M = 40.0
  # 市区转弯：低速时不要提前上百米就打灯，按「够用就好」的窗口。
  URBAN_TURN_SPEED_MPS = 16.0
  TURN_LOOKAHEAD_S = 4.0        # 转弯灯按 4 秒提前量计算（低速准，高速也够）
  TURN_LOOKAHEAD_MIN_M = 25.0
  TURN_LOOKAHEAD_MAX_M = 100.0
  RESTART_PULSE_NS = 2_000_000_000       # 转弯中停车后起步，补亮 2 秒
  RESTART_PULSE_DISTANCE_M = 25.0        # 只在这个距离内补灯
  RESTART_STOP_SPEED_MPS = 0.3
  RESTART_GO_SPEED_MPS = 1.5
  TURN_LAMP_MAX_NS = 20_000_000_000  # 转弯灯硬上限：超过 20 秒强制熄灭
  URBAN_TURN_HOLD_NS = 0             # 不再额外保持，转弯由车端自己维持
  SLOW_IMMEDIATE_MAX_M = 150.0    # 低速时并道/匝道窗口上限，避免提前几百米亮灯
  MAX_LOOKAHEAD_M = 250.0
  LOOKAHEAD_MARGIN_M = 20.0
  TURN_CLEAR_STABLE_NS = 500_000_000
  MANEUVER_DIRECTIONS = {
    "slightLeft": LaneIntentDirection.left,
    "turnLeft": LaneIntentDirection.left,
    "sharpLeft": LaneIntentDirection.left,
    "uTurnLeft": LaneIntentDirection.left,
    "exitLeft": LaneIntentDirection.left,
    "rampLeft": LaneIntentDirection.left,
    "mergeLeft": LaneIntentDirection.left,
    "slightRight": LaneIntentDirection.right,
    "turnRight": LaneIntentDirection.right,
    "sharpRight": LaneIntentDirection.right,
    "uTurnRight": LaneIntentDirection.right,
    "exitRight": LaneIntentDirection.right,
    "rampRight": LaneIntentDirection.right,
    "mergeRight": LaneIntentDirection.right,
  }

  def __init__(self) -> None:
    self._active_key: tuple[str, int, int] | None = None
    self._active_direction = LaneIntentDirection.none
    self._active_since_ns = 0
    self._plan_gap_since_ns: int | None = None
    self._completion_hold = False
    self._stopped_since_ns = 0
    self._pulse_until_ns = 0
    self._arrive_since_ns = 0
    self._suppress_until_ns = 0
    self._turn_clear_since_ns = 0

  def _reset(self, reason: str = "idle") -> NavLaneIntent:
    self._active_key = None
    self._active_direction = LaneIntentDirection.none
    self._active_since_ns = 0
    self._plan_gap_since_ns = None
    self._completion_hold = False
    self._turn_clear_since_ns = 0
    return NavLaneIntent(reason=reason)

  def update(self, plan: NavTurnPlan, *, speed_mps: float, now_ns: int,
             turn_geometry_active: bool = False, lookahead_time_s: float | None = None,
             lookahead_distance_m: float | None = None) -> NavLaneIntent:
    direction = self.MANEUVER_DIRECTIONS.get(plan.maneuver, LaneIntentDirection.none)
    event_key = (plan.session_id, plan.route_revision, plan.maneuver_event_id)

    # 转弯中停过车（等行人/让行），再起步时补亮 2 秒，提醒后车本车正在转弯。
    if speed_mps <= self.RESTART_STOP_SPEED_MPS:
      if self._stopped_since_ns == 0:
        self._stopped_since_ns = now_ns
    else:
      if (self._stopped_since_ns and speed_mps >= self.RESTART_GO_SPEED_MPS
          and now_ns - self._stopped_since_ns >= 500_000_000
          and direction is not LaneIntentDirection.none
          and 0.0 <= plan.distance_m <= self.RESTART_PULSE_DISTANCE_M):
        self._pulse_until_ns = now_ns + self.RESTART_PULSE_NS
      self._stopped_since_ns = 0
    if (self._pulse_until_ns and now_ns < self._pulse_until_ns
        and direction is not LaneIntentDirection.none):
      self._active_key = event_key
      self._active_direction = direction
      self._active_since_ns = now_ns
      return NavLaneIntent(
        signal_requested=True, direction=direction, request_id=plan.maneuver_event_id,
        target_lane_index=-1, reason="turnRestartPulse",
      )

    # 已到达路口并在转弯：保持灯，但超过 ARRIVE_HOLD_NS 仍未推进就释放，
    # 避免转完弯灯一直亮着。
    if plan.valid and 0.0 <= plan.distance_m <= ARRIVE_DISTANCE_M:
      if self._arrive_since_ns == 0:
        self._arrive_since_ns = now_ns
      elif self._active_key is not None and now_ns - self._arrive_since_ns > (
          self.URBAN_TURN_HOLD_NS if (plan.maneuver in self.TURN_MANEUVERS
                                      and speed_mps < self.URBAN_TURN_SPEED_MPS) else ARRIVE_HOLD_NS):
        self._arrive_since_ns = 0
        self._suppress_until_ns = now_ns + POST_TURN_SUPPRESS_NS
        return self._reset("turnCompleted")
    else:
      self._arrive_since_ns = 0

    # 刚通过路口的一小段时间内不再为下一个机动点灯。
    if self._suppress_until_ns and now_ns < self._suppress_until_ns and self._active_key is None:
      return NavLaneIntent(reason="postTurnSuppress")

    if self._active_key is not None:
      # 路口转弯灯的硬上限：导航距离卡住不动时也要能自动熄灭。
      if (self._active_direction is not LaneIntentDirection.none
          and now_ns - self._active_since_ns > self.TURN_LAMP_MAX_NS):
        return self._reset("turnLampTimeout")
      if now_ns - self._active_since_ns > self.SIGNAL_TIMEOUT_NS:
        return self._reset("turnSignalTimeout")
      if event_key != self._active_key or direction != self._active_direction:
        # 只按 session 判断路线连续性：导航每次路径刷新都会递增 routeRevision，
        # 旧逻辑会因此每 1-2 秒重置一次打灯，导致灯闪、并道被取消。
        route_continuous = plan.session_id == self._active_key[0]
        if not route_continuous:
          return self._reset("turnChanged")
        # 模型不一定给出 turnGeometryActive；低车速（正在转弯）同样按完成态处理，
        # 否则每换一个导航 step 就会把灯掐灭再点亮。
        # 只有方向一致才沿用旧方向；方向变了必须切到新方向，否则会出现
        # 「左转却亮右灯」的情况。
        # 完成保持已关闭：转弯过程中不再沿用旧灯，事件变化即释放（车端会在转弯中自行保持）。
        return self._reset("turnChanged")
        same_direction = direction == self._active_direction
        # 新机动是「明确的反方向」时立刻切换，不能走完成保持：
        # 否则上一次转弯的 _completion_hold 会把下一个右转一直压住。
        if direction is not LaneIntentDirection.none and not same_direction:
          return self._reset("turnDirectionChanged")
        # 机动变成 none 且车辆仍在转弯中 → 短暂保持旧方向。
        if direction is LaneIntentDirection.none and not (turn_geometry_active or speed_mps <= TURN_HOLD_SPEED_MPS):
          return self._reset("turnChanged")
        if same_direction and (turn_geometry_active or speed_mps <= TURN_HOLD_SPEED_MPS):
          self._completion_hold = True
          self._turn_clear_since_ns = 0
        elif self._completion_hold:
          if self._turn_clear_since_ns == 0:
            self._turn_clear_since_ns = now_ns
          elif now_ns - self._turn_clear_since_ns > self.TURN_CLEAR_STABLE_NS:
            return self._reset("turnChanged")
        else:
          return self._reset("turnChanged")
        return NavLaneIntent(
          signal_requested=True,
          direction=self._active_direction,
          # The next guidance event does not own the still-active turn lamp.
          request_id=self._active_key[2],
          target_lane_index=-1,
          reason="turnCompletion",
        )
      self._completion_hold = False
      self._turn_clear_since_ns = 0
      if not plan.valid:
        if self._plan_gap_since_ns is None:
          self._plan_gap_since_ns = now_ns
        if now_ns - self._plan_gap_since_ns <= self.PLAN_GAP_GRACE_NS:
          return NavLaneIntent(
            signal_requested=True,
            direction=self._active_direction,
            request_id=plan.maneuver_event_id,
            target_lane_index=-1,
            reason="turnApproachGrace",
          )
        return self._reset("turnUnavailable")
      else:
        self._plan_gap_since_ns = None
        return NavLaneIntent(
          signal_requested=True,
          direction=self._active_direction,
          request_id=plan.maneuver_event_id,
          target_lane_index=-1,
          reason="turnApproach",
        )

    if not plan.valid or direction == LaneIntentDirection.none or plan.maneuver_event_id == 0:
      return self._reset("turnUnavailable")

    lookahead_m = max(self.MIN_LOOKAHEAD_M, min(
      self.MAX_LOOKAHEAD_M, max(0.0, speed_mps) * (self.LOOKAHEAD_TIME_S if lookahead_time_s is None else lookahead_time_s) + self.LOOKAHEAD_MARGIN_M,
    ))
    if lookahead_distance_m:
      # Turn-lane lookahead (UI setting) extends the lamp window so an announced turn arms the lamp
      # hundreds of metres out; 300 m keeps it from blinking through an entire road.
      lookahead_m = min(300.0, max(lookahead_m, float(lookahead_distance_m)))
    # 市区低速转弯：压缩打灯窗口，避免普通道路提前 100 m 就亮灯。
    # 转弯灯一律按「速度 × 4 秒」提前量：30 km/h 约 33 米，50 km/h 约 56 米。
    if plan.maneuver in self.TURN_MANEUVERS:
      lookahead_m = min(self.TURN_LOOKAHEAD_MAX_M,
                        max(self.TURN_LOOKAHEAD_MIN_M, max(0.0, speed_mps) * self.TURN_LOOKAHEAD_S))
    if (plan.maneuver in self.IMMEDIATE_ARM_MANEUVERS
        and speed_mps < self.URBAN_TURN_SPEED_MPS):
      lookahead_m = min(lookahead_m, self.SLOW_IMMEDIATE_MAX_M)
    if plan.maneuver in self.IMMEDIATE_ARM_MANEUVERS and plan.distance_m <= self.IMMEDIATE_ARM_MAX_M.get(plan.maneuver, 600.0):
      lookahead_m = max(lookahead_m, plan.distance_m)
    # 到达路口时导航距离会变成 0；旧条件要求 >0 会直接判定窗口外，导致转弯不打灯。
    if plan.distance_m > lookahead_m or plan.distance_m < -5.0:
      return self._reset("turnOutsideWindow")

    self._active_key = event_key
    self._active_direction = direction
    self._active_since_ns = now_ns
    self._plan_gap_since_ns = None
    return NavLaneIntent(
      signal_requested=True,
      direction=direction,
      request_id=plan.maneuver_event_id,
      target_lane_index=-1,
      reason="turnApproach",
    )

