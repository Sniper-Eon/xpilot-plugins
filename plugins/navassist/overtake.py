"""Slow-lead overtake manager, ported from navipilot's AutoOvertakeManager.

Modes: 0 off, 1 observe (log only), 2 auto. All inputs are C3-side.
"""
from __future__ import annotations

import math

CONTROLLED_ACCESS = frozenset(("expressway", "urban_expressway"))
MIN_LEAD_SPEED_MS = 13.9            # 50 km/h
MAX_CURVATURE_RATE = 0.02
MAX_STEERING_DEG = 15.0
EXECUTE_TIMEOUT_NS = 8_000_000_000
RETURN_MEMORY_NS = 30_000_000_000
RETURN_ADVANTAGE_KPH = 8.0
RETURN_HOLD_NS = 2_000_000_000

IDLE, PENDING, EXECUTING, OVERTAKEN, RETURNING, COOLDOWN = (
    "idle", "pending", "executing", "overtaken", "returning", "cooldown")

STYLE_CONFIRM = {0: 5, 1: 3, 2: 2}          # frames of confirmation
STYLE_DIFF_BONUS = {0: 2.0, 1: 0.0, 2: -2.0}  # km/h added to the speed-diff threshold

# 与 CP 对齐：目标车道无车时按「本车 +10 km/h」估算可达速度，
# 有车时按该车绝对速度估算；返回原车道要求至少 8 km/h 速度优势。
TARGET_SPEED_BOOST_KPH = 10.0
RETURN_MIN_ADVANTAGE_KPH = 8.0
RETURN_ADVANTAGE_FLOOR_KPH = 1.0
RETURN_HOLD_NS = 2_000_000_000          # 超越后至少保持 2 秒才考虑返回
NEAR_LEAD_DISTANCE_M = 20.0             # 原车道前车仍在这段距离内视为未完全超越
TBT_BIAS_DISTANCE_M = 3000.0            # 距转向点 3 km 内开始偏向转向侧超车
TBT_STOP_DISTANCE_M = 1000.0            # 距转向点 1 km 内不再超车
TBT_OPPOSITE_DIFF_MIN_KPH = 15.0        # 反向超车在 3 km 处要求的最低速度差
TBT_OPPOSITE_DIFF_MAX_KPH = 40.0        # 反向超车在 1 km 处要求的最低速度差



def _f(value, default=0.0):
  try:
    out = float(value)
    return out if math.isfinite(out) else default
  except (TypeError, ValueError):
    return default


def _lead0(model):
  try:
    leads = list(getattr(model, 'leadsV3', []) or [])
  except (AttributeError, TypeError):
    return None
  if not leads:
    return None
  lead = leads[0]
  return _f(getattr(lead, 'prob', 0.0)), _f(getattr(lead, 'x', 0.0)), _f(getattr(lead, 'v', 0.0))


def _curvature_rate(model):
  try:
    rate = getattr(model, 'orientationRate', None)
    values = [abs(_f(v)) for v in getattr(rate, 'z', [])]
    return max(values) if values else 0.0
  except (AttributeError, TypeError):
    return 0.0


class OvertakeController:
  def __init__(self):
    self.state = IDLE
    self.since = 0
    self.direction = "none"
    self.streak = 0
    self.reason = "idle"
    self.cooldown_until = 0
    self.original_lane = None
    self.passed_at = 0
    self.count = 0
    self.advantage_kph = None

  def reset(self, reason: str = "reset") -> None:
    self.state, self.since, self.direction = IDLE, 0, "none"
    self.streak, self.reason = 0, reason

  def _road_ok(self, road_kind, settings=None):
    return road_kind in CONTROLLED_ACCESS

  def _tbt_gate(self, nav, settings):
    """Do not pass against an upcoming turn, and stop near the turn."""
    try:
      maneuver = str(nav.get('maneuver', 'none'))
      distance = float(nav.get('maneuverDistanceM') or 0.0)
    except (TypeError, ValueError):
      return ''
    turn_left = maneuver in ('turnLeft', 'sharpLeft', 'uTurnLeft', 'exitLeft', 'rampLeft')
    turn_right = maneuver in ('turnRight', 'sharpRight', 'uTurnRight', 'exitRight', 'rampRight')
    if (turn_left or turn_right) and 0 < distance < float(settings.overtake_turn_m):
      return '接近转弯点'
    if (turn_left or turn_right) and 0 < distance < TBT_STOP_DISTANCE_M:
      return '接近转向点禁止超车'
    return ''

  def _tbt_bias(self, nav):
    """前方转向点方向：返回 ('left'|'right'|None, 距离米)。"""
    maneuver = str(nav.get('maneuver', 'none'))
    try:
      distance = float(nav.get('maneuverDistanceM') or 0.0)
    except (TypeError, ValueError):
      return None, 0.0
    if distance <= 0.0 or distance > TBT_BIAS_DISTANCE_M:
      return None, distance
    if maneuver in ('turnLeft', 'sharpLeft', 'uTurnLeft', 'exitLeft', 'rampLeft'):
      return 'left', distance
    if maneuver in ('turnRight', 'sharpRight', 'uTurnRight', 'exitRight', 'rampRight'):
      return 'right', distance
    return None, distance

  def _opposite_allowed(self, car, model, nav, side):
    """反向超车要求更高的速度差，距离转向点越近要求越高（CP 的 TBT 偏好抑制）。"""
    bias, distance = self._tbt_bias(nav)
    if bias is None or bias == side:
      return True, ''
    lead = _lead0(model)
    if lead is None:
      return False, '反向超车但前车缺失'
    diff_kph = (_f(getattr(car, 'vEgo', 0.0)) - lead[2]) * 3.6
    ratio = max(0.0, min(1.0, (TBT_BIAS_DISTANCE_M - max(distance, TBT_STOP_DISTANCE_M)) /
                          (TBT_BIAS_DISTANCE_M - TBT_STOP_DISTANCE_M)))
    required = TBT_OPPOSITE_DIFF_MIN_KPH + ratio * (TBT_OPPOSITE_DIFF_MAX_KPH - TBT_OPPOSITE_DIFF_MIN_KPH)
    if diff_kph < required:
      return False, '反向超车速度差不足'
    return True, ''

  def _gates(self, *, car, model, nav, settings, road_kind, lateral_active):
    if road_kind not in CONTROLLED_ACCESS:
      return '仅受控道路'
    if not lateral_active:
      return '辅助未激活'
    if bool(getattr(car, 'steeringPressed', False)):
      return '驾驶员接管'
    if bool(getattr(car, 'brakePressed', False)) or bool(getattr(car, 'gasPressed', False)):
      return '驾驶员踩踏板'
    if bool(getattr(car, 'leftBlinker', False)) or bool(getattr(car, 'rightBlinker', False)):
      return '转向灯已开'
    if abs(_f(getattr(car, 'steeringAngleDeg', 0.0))) > MAX_STEERING_DEG:
      return '方向盘角过大'
    tbt = self._tbt_gate(nav, settings)
    if tbt:
      return tbt
    lead = _lead0(model)
    if lead is None:
      return '前车缺失'
    prob, lead_x, lead_v = lead
    if prob < 0.5 or not 0.0 < lead_x < float(settings.overtake_lead_max_m):
      return '前车过远或置信度低'
    if lead_v < MIN_LEAD_SPEED_MS:
      return '前车过慢'
    if _curvature_rate(model) >= MAX_CURVATURE_RATE:
      return '弯道中'
    if _f(getattr(car, 'vEgo', 0.0)) < float(settings.overtake_min_kph) / 3.6:
      return '速度过低'
    return ''

  def _need(self, car, model, settings):
    lead = _lead0(model)
    if lead is None:
      return False, '前车缺失'
    _, lead_x, lead_v = lead
    v_ego = _f(getattr(car, 'vEgo', 0.0))
    diff_kph = (v_ego - lead_v) * 3.6
    threshold = float(settings.overtake_diff_kph) + STYLE_DIFF_BONUS.get(int(settings.overtake_style), 0.0)
    if int(settings.overtake_early):
      if (lead_v <= v_ego * 0.8 and lead_v >= MIN_LEAD_SPEED_MS and diff_kph >= 20.0
          and 30.0 <= lead_x <= 100.0):
        return True, '远距离超车'
    return diff_kph >= threshold, '速度差不足'

  def _side(self, direction, *, topology, left_blocked, right_blocked,
            blindspot_left, blindspot_right):
    at_edge = False
    count = int(topology.get('visibleLaneCount', 0) or 0)
    ego = int(topology.get('egoLaneIndexFromLeft', -1) or -1)
    if direction == 'left':
      if left_blocked or blindspot_left:
        return False, '左侧盲区'
      if not topology.get('leftNeighborExists', False):
        return False, '左侧无邻道'
      at_edge = count > 1 and ego == 0
    else:
      if right_blocked or blindspot_right:
        return False, '右侧盲区'
      if not topology.get('rightNeighborExists', False):
        return False, '右侧无邻道'
      at_edge = count > 1 and ego == count - 1
    if at_edge:
      return False, '该侧实线'
    return True, ''

  def _pick_side(self, topology, left_blocked, right_blocked, blindspot_left, blindspot_right,
                 prefer=None):
    for candidate in ((prefer,) if prefer in ('left', 'right') else ()) + ('left', 'right'):
      ok, reason = self._side(candidate, topology=topology, left_blocked=left_blocked,
                              right_blocked=right_blocked, blindspot_left=blindspot_left,
                              blindspot_right=blindspot_right)
      if ok:
        return candidate, ''
    return 'none', '两侧不可用'

  def _lead_ahead_in_original_lane(self, model, threshold_m=NEAR_LEAD_DISTANCE_M):
    """原车道前车是否仍在阈值内（未完全超越）。"""
    lead = _lead0(model)
    if lead is None:
      return False
    prob, x, _ = lead
    return prob >= 0.5 and 0.0 < x < threshold_m

  def _return_advantage_kph(self, car, model, original_lane, ego_lane, blindspot_left,
                            blindspot_right, left_blocked, right_blocked):
    """估算回到原车道的速度优势（CP 的 isReturnEfficient）。"""
    v_ego_kph = _f(getattr(car, 'vEgo', 0.0)) * 3.6
    # 原车道预期速度：有前车按前车速度，无前车按本车速度
    lead = _lead0(model)
    original_expected = _f(lead[2]) * 3.6 if lead is not None else v_ego_kph
    # 目标车道（原车道）是否有车：用盲区与邻道占用判断
    going_left = original_lane < ego_lane
    occupied = (blindspot_left or left_blocked) if going_left else (blindspot_right or right_blocked)
    target_speed = v_ego_kph if occupied else v_ego_kph + TARGET_SPEED_BOOST_KPH
    return target_speed - original_expected

  def _return_efficient(self, car, model, now_ns, original_lane, ego_lane,
                        blindspot_left, blindspot_right, left_blocked, right_blocked):
    advantage = self._return_advantage_kph(car, model, original_lane, ego_lane,
                                           blindspot_left, blindspot_right,
                                           left_blocked, right_blocked)
    # 在超车道待得越久，门槛越低（CP 的时间递减）
    seconds = max(0.0, (now_ns - self.passed_at) / 1e9) if self.passed_at else 0.0
    if seconds > 30.0:
      bonus = RETURN_MIN_ADVANTAGE_KPH - RETURN_ADVANTAGE_FLOOR_KPH
    elif seconds > 15.0:
      bonus = 2.0 + (seconds - 15.0) / 15.0 * 6.0
    else:
      bonus = 0.0
    threshold = max(RETURN_ADVANTAGE_FLOOR_KPH, RETURN_MIN_ADVANTAGE_KPH - bonus)
    self.advantage_kph = advantage
    return advantage >= threshold

  def _enter_cooldown(self, now_ns, settings, reason):
    self.state = COOLDOWN
    self.since = now_ns
    self.cooldown_until = now_ns + int(settings.overtake_cooldown_s) * 1_000_000_000
    self.reason = reason
    self.direction = 'none'

  def update(self, *, car, model, topology, nav, now_ns, settings, road_kind,
             left_blocked, right_blocked, blindspot_left, blindspot_right,
             lateral_active, lane_change_state='off'):
    mode = int(settings.overtake_mode)
    if mode <= 0:
      if self.state != IDLE:
        self.reset('disabled')
      return self.snapshot('disabled')
    if mode == 1:
      # observe-only: keep the state machine but never request
      out = self._step(car=car, model=model, topology=topology, nav=nav, now_ns=now_ns,
                       settings=settings, road_kind=road_kind, left_blocked=left_blocked,
                       right_blocked=right_blocked, blindspot_left=blindspot_left,
                       blindspot_right=blindspot_right, lateral_active=lateral_active,
                       lane_change_state=lane_change_state, observe=True)
      out['request'] = False
      return out
    return self._step(car=car, model=model, topology=topology, nav=nav, now_ns=now_ns,
                      settings=settings, road_kind=road_kind, left_blocked=left_blocked,
                      right_blocked=right_blocked, blindspot_left=blindspot_left,
                      blindspot_right=blindspot_right, lateral_active=lateral_active,
                      lane_change_state=lane_change_state, observe=False)

  def _step(self, *, car, model, topology, nav, now_ns, settings, road_kind,
            left_blocked, right_blocked, blindspot_left, blindspot_right,
            lateral_active, lane_change_state, observe):
    ego = int(topology.get('egoLaneIndexFromLeft', -1) or -1)

    if self.state == COOLDOWN:
      if now_ns < self.cooldown_until:
        return self.snapshot('冷却中')
      self.reset('冷却结束')

    if self.state == EXECUTING:
      if now_ns - self.since > EXECUTE_TIMEOUT_NS:
        self._enter_cooldown(now_ns, settings, '变道超时')
        return self.snapshot(self.reason)
      if self.original_lane is not None and ego >= 0 and ego != self.original_lane:
        self.state, self.since = OVERTAKEN, now_ns
        self.passed_at = now_ns
        self.reason = '已变道'
        return self.snapshot(self.reason)
      return self.snapshot('执行中')

    if self.state == OVERTAKEN:
      if now_ns - self.since > RETURN_MEMORY_NS:
        self._enter_cooldown(now_ns, settings, '超车完成')
        return self.snapshot(self.reason)
      if now_ns - self.since > RETURN_HOLD_NS and self.original_lane is not None and ego >= 0:
        target_dir = 'left' if self.original_lane < ego else 'right' if self.original_lane > ego else 'none'
        if target_dir != 'none':
          # 1) 必须完全超越原车道前车
          if self._lead_ahead_in_original_lane(model):
            self.reason = '等待完全超越'
            return self.snapshot(self.reason)
          # 2) 返回后要有速度优势，避免来回摆动（CP isReturnEfficient）
          if not self._return_efficient(car, model, now_ns, self.original_lane, ego,
                                        blindspot_left, blindspot_right,
                                        left_blocked, right_blocked):
            self.reason = '返回收益不足'
            return self.snapshot(self.reason)
          ok, reason = self._side(target_dir, topology=topology, left_blocked=left_blocked,
                                  right_blocked=right_blocked, blindspot_left=blindspot_left,
                                  blindspot_right=blindspot_right)
          if ok:
            self.state, self.since, self.direction = RETURNING, now_ns, target_dir
            self.reason = '返回原车道'
            return self.snapshot(self.reason)
          self.reason = '等待返回: ' + reason
      return self.snapshot(self.reason or '超车完成')

    if self.state == RETURNING:
      if now_ns - self.since > EXECUTE_TIMEOUT_NS:
        self._enter_cooldown(now_ns, settings, '返回超时')
        return self.snapshot(self.reason)
      if self.original_lane is not None and ego == self.original_lane:
        self._enter_cooldown(now_ns, settings, '已返回原车道')
        return self.snapshot(self.reason)
      return self.snapshot('返回中')

    fail = self._gates(car=car, model=model, nav=nav, settings=settings,
                       road_kind=road_kind, lateral_active=lateral_active)
    if fail:
      if self.state == PENDING:
        self.reset(fail)
      self.reason = fail
      return self.snapshot(fail)

    need, why = self._need(car, model, settings)
    if not need:
      self.streak = 0
      if self.state == PENDING:
        self.reset(why)
      self.reason = why
      return self.snapshot(why)

    self.streak += 1
    confirm = STYLE_CONFIRM.get(int(settings.overtake_style), 3)
    if self.streak < confirm:
      self.reason = '确认中'
      return self.snapshot(self.reason)

    bias, _ = self._tbt_bias(nav)
    direction, side_reason = self._pick_side(topology, left_blocked, right_blocked,
                                             blindspot_left, blindspot_right, prefer=bias)
    if direction == 'none':
      self.reason = side_reason
      return self.snapshot(side_reason)

    allowed, opposite_reason = self._opposite_allowed(car, model, nav, direction)
    if not allowed:
      self.reason = opposite_reason
      return self.snapshot(opposite_reason)

    if self.state == PENDING and direction == self.direction:
      if now_ns - self.since < int(settings.overtake_delay_ms) * 1_000_000:
        self.reason = '等待变道'
        return self.snapshot(self.reason)
      self.state, self.since = EXECUTING, now_ns
      self.original_lane = ego
      self.count += 1
      self.reason = '执行变道'
      return self.snapshot(self.reason)

    self.state, self.since, self.direction = PENDING, now_ns, direction
    self.reason = '待执行 ' + direction
    return self.snapshot(self.reason)

  def snapshot(self, reason: str) -> dict:
    request = self.state in (EXECUTING, RETURNING)
    return dict(state=self.state, reason=reason or self.reason,
                direction=self.direction if request else 'none',
                request=request, count=self.count, original_lane=self.original_lane)
