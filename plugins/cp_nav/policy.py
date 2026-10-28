"""CP may prepare or veto SP lane changes, never bypass its automatic mode."""
import time

from openpilot.tesla.lane_policy import LaneChangeLimits
from .settings import read


def side(direction):
  value = str(getattr(direction, 'raw', direction)).lower()
  return {'1': 'left', '2': 'right'}.get(value, value)


class CPLanePolicy:
  def __init__(self, params):
    self.params = params
    self._msgs = None
    self.owned = None
    self._settings = None
    self._next = 0.0

  def _read(self):
    now = time.monotonic()
    if self._settings is None or now >= self._next:
      self._settings = read(self.params)
      self._next = now + 1.0
    return self._settings

  def intent(self):
    if self._msgs is None:
      from openpilot.tesla.plugins import PluginMsgs
      self._msgs = PluginMsgs()
    d = self._msgs.fresh('lanes.intent').get('cp_nav') or {}
    if self._read().enabled and d.get('valid') is True and d.get('signalRequested') is True:
      self.owned = d.get('direction')
      return d
    return {}

  def allow(self, carstate, direction, default):
    d = self.intent()
    if d:
      settings = self._read()
      return bool(settings.lane_changes and default and not d.get('turnOnly')
                  and d.get('laneChangeAllowed') is True
                  and d.get('direction') == side(direction))
    return bool(default and self.owned is None)

  def constraints(self, carstate, direction):
    d = self.intent()
    if d:
      settings = self._read()
      opposite = getattr(carstate, 'rightBlinker' if d.get('direction') == 'left' else 'leftBlinker', True)
      turn = d.get('turnOnly') is True
      ready = bool(settings.lane_changes and not opposite and not turn
                   and d.get('laneChangeAllowed') is True)
      return LaneChangeLimits(allow_start=ready, allow_continue=ready,
                              turn_only=turn and not opposite, suppress_turn=not turn)
    if self.owned is not None:
      if getattr(carstate, 'leftBlinker', False) or getattr(carstate, 'rightBlinker', False):
        return LaneChangeLimits(allow_start=False, allow_continue=False, suppress_turn=True)
      self.owned = None
    return LaneChangeLimits()
