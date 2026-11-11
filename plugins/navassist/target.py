"""long_target hook: the bounded navigation speed ceiling before a maneuver."""
from __future__ import annotations

import time

from .settings import read as read_settings
from .speed import NavigationSpeedCeiling


class NavSpeedTarget:
  def __init__(self, params):
    self.params = params
    self.settings = read_settings(params)
    self.ceiling = NavigationSpeedCeiling(self.settings)
    self._msgs = None
    self._next_settings = 0.0

  def _fresh(self) -> dict:
    try:
      if self._msgs is None:
        from openpilot.tesla.plugins import PluginMsgs
        self._msgs = PluginMsgs()
      values = self._msgs.fresh("nav.state")
      return values.get('navassist', {})
    except Exception:
      return {}

  def update(self, sm, v_ego: float, v_cruise: float):
    now = time.monotonic()
    if now >= self._next_settings:
      self._next_settings = now + 1.0
      try:
        self.settings = read_settings(self.params)
        self.ceiling.settings = self.settings
      except Exception:
        pass
    try:
      cs = sm["carState"]
      cc = sm["carControl"]
      override = bool(cs.gasPressed or cs.brakePressed or cc.cruiseControl.override)
      planner_ready = bool(cc.enabled)
    except (KeyError, AttributeError):
      override, planner_ready = True, False
    nav = self._fresh()
    out = self.ceiling.update(nav, v_ego=v_ego, v_cruise=v_cruise, enabled=self.settings.enabled,
                              driver_override=override, planner_ready=planner_ready)
    # 诊断：把调速结果写给 navassist 进程，日志里能看到「有没有减速/为什么没减」。
    try:
      if now >= getattr(self, '_next_diag', 0.0):
        self._next_diag = now + 0.5
        import json as _json
        with open('/tmp/navassist_speed.json', 'w') as f:
          _json.dump({'enabled': bool(self.settings.enabled),
                      'turnSlowdown': bool(self.settings.turn_slowdown_enabled),
                      'plannerReady': bool(planner_ready), 'override': bool(override),
                      'vEgo': round(float(v_ego), 2), 'vCruise': round(float(v_cruise), 2),
                      'output': None if out is None else round(float(out), 2),
                      'target': round(float(self.ceiling._target), 2),
                      'active': bool(self.ceiling.is_active),
                      'maneuver': str(nav.get('maneuver', 'none')),
                      'distanceM': round(float(nav.get('distanceM', 0.0) or 0.0), 1),
                      'navValid': bool(nav.get('valid')), 'navStale': bool(nav.get('stale'))}, f)
    except Exception:
      pass
    return out
