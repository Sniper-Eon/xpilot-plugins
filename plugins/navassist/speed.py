"""Bounded navigation speed ceiling before a supported maneuver.

Only lowers the common cruise target; never requests a stop or acceleration. The host's long_target merges this
with SP's own targets by taking the minimum, so lead/FCW/model limits still win."""
from __future__ import annotations

import math

from .settings import NavSettings

COMFORT_BRAKE = 1.2
ACTUATION_DELAY_S = 1.0
ADMISSION_MARGIN_M = 5.0
ACTIVATION_MARGIN_M = 25.0
TURN_ACTIVATION_MARGIN_M = 60.0   # 转弯类提前 60 米开始减速
COMFORT_DECEL = 0.9              # 舒适减速度 m/s^2（刹车曲线）
OUTPUT_DECEL_RATE = 1.2          # 允许速度每秒最多下降多少 m/s，避免跳变
# 按高德机动类型区分弯道形态（不再一套逻辑套所有弯）
MANEUVER_SPEEDS_KPH = {
  "turn_left": 25.0, "turn_right": 25.0,       # 普通路口转弯
  "sharp_left": 22.0, "sharp_right": 22.0,     # 直角/急弯
  "u_turn_left": 15.0, "u_turn_right": 15.0,   # 掉头
  "roundabout": 25.0,                          # 环岛
  "ramp_left": 55.0, "ramp_right": 55.0,       # 匝道（大曲率）
  "slight_left": 55.0, "slight_right": 55.0,   # 缓弯
  "exit_left": 55.0, "exit_right": 55.0,       # 出口
}
MAX_MANEUVER_DISTANCE_M = 2_000.0
MAX_NAV_SPEED_MPS = 70.0 / 3.6
MIN_TARGET_SPEED_MPS = 2.0
RELEASE_ACCEL_MPS2 = 1.0
DT = 0.05
TURN_MANEUVERS = frozenset(("turn_left", "turn_right", "sharp_left", "sharp_right",
                                  "u_turn_left", "u_turn_right", "roundabout"))

TARGET_SPEEDS = {
  "slight_left": 12.5, "slight_right": 12.5,   # 45 km/h：往左/右前方行驶不该压到 29
  "turn_left": 5.0, "turn_right": 5.0,
  "sharp_left": 6.5, "sharp_right": 6.5,   # 23 km/h
  "u_turn_left": 2.5, "u_turn_right": 2.5,
  "exit_left": 12.5, "exit_right": 12.5,   # 45 km/h
  "ramp_left": 12.5, "ramp_right": 12.5,   # 45 km/h
  "roundabout": 6.0,
}


class NavigationSpeedCeiling:
  def __init__(self, settings: NavSettings):
    self.settings = settings
    self.output = None
    self.is_active = False
    self._event_key = None
    self._admitted = False
    self._rejected = False
    self._activated = False
    self._target = 0.0
    self._required = 0.0
    self._releasing = False

  def reset(self) -> None:
    self.output = None
    self.is_active = False
    self._event_key = None
    self._admitted = self._rejected = self._activated = False
    self._releasing = False

  @staticmethod
  def _required_distance(v_ego: float, target: float) -> float:
    braking = max(0.0, v_ego * v_ego - target * target) / (2.0 * COMFORT_BRAKE)
    return braking + v_ego * ACTUATION_DELAY_S

  def _target_for(self, nav: dict) -> float | None:
    maneuver = str(nav.get("maneuver", "none"))
    kph = MANEUVER_SPEEDS_KPH.get(maneuver)
    if kph is not None:
      default = kph / 3.6
      # 用户的转弯限速只能把普通转弯压得更低，不能把它抬高
      if maneuver in ("turn_left", "turn_right"):
        default = min(default, self.settings.turn_speed_kph / 3.6)
    else:
      default = TARGET_SPEEDS.get(maneuver)
    if default is None:
      return None
    advisory = float(nav.get("advisorySpeedMps") or 0.0)
    if advisory > 0.0:
      return max(MIN_TARGET_SPEED_MPS, min(default, advisory))
    return default

  def _release(self, v_cruise: float) -> None:
    self.is_active = False
    if self.output is None:
      self._releasing = False
      return
    self.output = min(v_cruise, self.output + RELEASE_ACCEL_MPS2 * DT)
    self._releasing = self.output < v_cruise - 1e-3
    if not self._releasing:
      self.output = None

  def _pause(self) -> None:
    if self._activated:
      self._rejected = True
    self._admitted = False

  def update(self, nav: dict, *, v_ego: float, v_cruise: float, enabled: bool,
             driver_override: bool, planner_ready: bool = True) -> float | None:
    if (not enabled or not self.settings.turn_slowdown_enabled or driver_override or not planner_ready
        or not math.isfinite(v_ego) or not 0.0 <= v_ego <= MAX_NAV_SPEED_MPS):
      self._pause()
      self._release(v_cruise)
      return self.output
    if not nav.get("valid") or nav.get("stale"):
      self._pause()
      self._release(v_cruise)
      return self.output
    target = self._target_for(nav)
    distance = float(nav.get("distanceM", 0.0))
    key = (str(nav.get("sessionId", "")), int(nav.get("routeRevision", 0)), int(nav.get("maneuverEventId", 0)))
    if (target is None or key[2] == 0 or not math.isfinite(distance)
        or not 0.0 <= distance <= MAX_MANEUVER_DISTANCE_M):
      self._pause()
      self._release(v_cruise)
      return self.output
    required = self._required_distance(v_ego, target)
    if key != self._event_key or (not self._admitted and not self._rejected):
      self._event_key = key
      self._target = target
      self._required = required
      self._admitted = distance >= required + ADMISSION_MARGIN_M
      self._rejected = not self._admitted
      self._activated = False
    if self._rejected or not self._admitted:
      self._release(v_cruise)
      return self.output
    if not self._activated:
      self._required = max(self._required, required)
      if distance < self._required:
        self._rejected = True
        self._release(v_cruise)
        return self.output
      margin = (TURN_ACTIVATION_MARGIN_M if str(nav.get("maneuver", "")) in TURN_MANEUVERS
                else ACTIVATION_MARGIN_M)
      if distance > self._required + margin:
        self._release(v_cruise)
        return self.output
      self._activated = True
    self.is_active = True
    self._releasing = False
    # 刹车曲线：离路口越远允许速度越高，减速度恒定且平缓。
    curve = math.sqrt(max(0.0, self._target * self._target + 2.0 * COMFORT_DECEL * max(0.0, distance)))
    limit = min(v_cruise, curve)
    if self.output is not None:
      # 允许速度每秒最多降 OUTPUT_DECEL_RATE，避免导航距离跳变造成急刹。
      limit = max(limit, self.output - OUTPUT_DECEL_RATE * DT)
    self.output = min(limit, v_ego)
    return self.output
