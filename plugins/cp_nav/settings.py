"""CP owns its master, execution modes and native navigation parameters."""
from dataclasses import dataclass


@dataclass(frozen=True)
class CPSettings:
  enabled: bool = False
  signals: bool = True
  lane_changes: bool = True
  speed_control: bool = True
  speed_raise: bool = False
  overtake_mode: int = 0
  driving_style: int = 1
  auto_turn: int = 2
  turn_kph: int = 20
  turn_end_s: int = 5
  decel_cms2: int = 120
  speed_factor_pct: int = 100
  road_offset_kph: int = 0
  speed_end_s: int = 5
  bump_kph: int = 30
  bump_time_s: int = 3
  rear_hold_m: int = 100
  curve_mode: int = 0
  curve_min_kph: int = 20
  curve_factor_pct: int = 100
  countdown_mode: int = 1
  max_kph: int = 120
  raise_step_kph: int = 10
  raise_interval_s: int = 3
  lane_delay_ms: int = 500
  overtake_min_kph: int = 70
  beep: bool = True


# Native keys are scoped aliases, never requests to mutate the SP/global keys.
NATIVE_KEYS = {
 'AutoNaviSpeedBumpSpeed':'bump_kph','AutoNaviSpeedBumpTime':'bump_time_s',
 'AutoNaviSpeedCtrlEnd':'speed_end_s','AutoNaviRearCameraHoldDistance':'rear_hold_m',
 'AutoNaviSpeedSafetyFactor':'speed_factor_pct','AutoNaviSpeedDecelRate':'decel_cms2',
 'AutoNaviCountDownMode':'countdown_mode','TurnSpeedControlMode':'curve_mode',
 'MapTurnSpeedFactor':'curve_factor_pct','AutoTurnControlSpeedTurn':'turn_kph',
 'AutoTurnControl':'auto_turn','AutoTurnControlTurnEnd':'turn_end_s',
 'AutoCurveSpeedLowerLimit':'curve_min_kph','AutoRoadSpeedLimitOffset':'road_offset_kph',
}


class NativeParams:
  def __init__(self, settings):self.settings=settings
  def get_int(self, key):
    if key in NATIVE_KEYS:return int(getattr(self.settings,NATIVE_KEYS[key]))
    if key=='AutoNaviSpeedCtrlMode':return 1
    return 0
  def get_float(self, key):return float(self.get_int(key))
  def get_bool(self, key):return key=='IsMetric'
  def get(self, key):
    if key=='LanguageSetting':return 'main_zh-CHS'
    return str(self.get_int(key))


def read(params):
  values={}
  for name, field in CPSettings.__dataclass_fields__.items():
    key='ExtCpNav'+''.join(part.capitalize() for part in name.split('_'))
    try:
      raw=params.get_bool(key) if isinstance(field.default,bool) else int(params.get(key,return_default=True))
    except (ValueError,TypeError,KeyError):raw=field.default
    values[name]=raw
  return CPSettings(**values)
