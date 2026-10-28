"""One audible notice when the navigation-requested lane change actually starts.

The request only arms a window; the chime fires on modelV2.meta.laneChangeState == laneChangeStarting, so a
blinker that is never executed stays silent.
"""
import time

from openpilot.cereal import log
from openpilot.tesla.plugin import PluginAlert
from .settings import read as read_settings

EXECUTION_WINDOW_S = 15.0
DIRECTIONS = {1: 'left', 2: 'right'}


class NavigationChime:
  def __init__(self, params):
    self.settings = read_settings(params)
    self._msgs = None
    self._request_key = None
    self._requested_at = 0.0
    self._last_fired = None

  def update(self, sm):
    if not self.settings.enabled or not self.settings.beep_enabled:
      return []
    if self._msgs is None:
      from openpilot.tesla.plugins import PluginMsgs
      self._msgs = PluginMsgs()
    now = time.monotonic()
    intent = self._msgs.fresh('lanes.intent').get('navassist') or {}
    if (intent.get('valid') and intent.get('signalRequested')
        and intent.get('direction') in ('left', 'right')):
      key = tuple(intent.get(k) for k in ('sessionId', 'routeRevision', 'maneuverEventId', 'requestId'))
      if key != self._request_key:
        self._request_key = key
        self._requested_at = now
    meta = sm['modelV2'].meta
    if meta.laneChangeState != log.LaneChangeState.laneChangeStarting:
      return []
    direction = DIRECTIONS.get(int(meta.laneChangeDirection))
    if direction is None or self._request_key is None or now - self._requested_at > EXECUTION_WINDOW_S:
      return []
    key = self._request_key + (direction,)
    if key == self._last_fired:
      return []
    self._last_fired = key
    return [PluginAlert('warning', 'Navigation turn signal', direction.capitalize())]
