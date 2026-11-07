"""Navigation policy settings, read from the host ParamsView (plugin.json declares the keys)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NavSettings:
  enabled: bool = True
  lane_change_enabled: bool = True
  turn_signal_enabled: bool = True
  turn_slowdown_enabled: bool = True
  turn_lane_lookahead_m: int = 1000
  exit_lane_lookahead_m: int = 2000
  signal_lead_time_s: int = 8
  turn_speed_kph: int = 30
  max_lane_changes: int = 5
  phone_assist_enabled: bool = False
  phone_lane_enabled: bool = False
  beep_enabled: bool = True
  # 超车（对照 navipilot AutoOvertakeManager）
  overtake_mode: int = 0
  overtake_style: int = 1
  overtake_min_kph: int = 70
  overtake_diff_kph: int = 10
  overtake_lead_max_m: int = 80
  overtake_turn_m: int = 2000
  overtake_delay_ms: int = 2500
  overtake_cooldown_s: int = 20
  overtake_early: int = 1


def _int(params, key: str, default: int, low: int, high: int) -> int:
  try:
    value = int(params.get(key, return_default=True))
  except (TypeError, ValueError):
    return default
  return value if low <= value <= high else default


def _bool(params, key: str, default: bool) -> bool:
  try:
    return bool(params.get_bool(key))
  except Exception:
    return default


def read(params) -> NavSettings:
  return NavSettings(
    enabled=_bool(params, "ExtNavAssistEnabled", False),
    lane_change_enabled=_bool(params, "ExtNavAssistLaneChange", True),
    turn_signal_enabled=_bool(params, "ExtNavAssistTurnSignal", True),
    turn_slowdown_enabled=_bool(params, "ExtNavAssistTurnSlowdown", True),
    turn_lane_lookahead_m=_int(params, "ExtNavAssistLookahead", 1000, 100, 1500),
    exit_lane_lookahead_m=_int(params, "ExtNavAssistExitLookahead", 2000, 300, 3000),
    signal_lead_time_s=_int(params, "ExtNavAssistSignalLead", 8, 3, 12),
    turn_speed_kph=_int(params, "ExtNavAssistTurnSpeed", 30, 10, 45),
    max_lane_changes=_int(params, "ExtNavAssistMaxChanges", 5, 1, 5),
    phone_assist_enabled=_bool(params, "ExtNavAssistPhoneBlindspot", False),
    phone_lane_enabled=_bool(params, "ExtNavAssistPhoneLane", False),
    beep_enabled=_bool(params, "ExtNavAssistBeep", True),
    overtake_mode=_int(params, "ExtNavAssistOvertake", 0, 0, 2),
    overtake_style=_int(params, "ExtNavAssistOvertakeStyle", 1, 0, 2),
    overtake_min_kph=_int(params, "ExtNavAssistOvertakeMinKph", 70, 50, 120),
    overtake_diff_kph=_int(params, "ExtNavAssistOvertakeDiffKph", 10, 5, 30),
    overtake_lead_max_m=_int(params, "ExtNavAssistOvertakeLeadMaxM", 80, 40, 150),
    overtake_turn_m=_int(params, "ExtNavAssistOvertakeTurnM", 2000, 500, 3000),
    overtake_delay_ms=_int(params, "ExtNavAssistOvertakeDelayMs", 2500, 1000, 5000),
    overtake_cooldown_s=_int(params, "ExtNavAssistOvertakeCooldownS", 20, 10, 60),
    overtake_early=_int(params, "ExtNavAssistOvertakeEarly", 1, 0, 1),
  )
