"""One audible notice when the navigation-requested lane change actually starts.

Requires a fresh matching navigation request, physical lamp and actual SP
laneChangeStarting; a blinker that is never executed stays silent.
"""
import time

from openpilot.cereal import log
from openpilot.tesla.plugin import PluginAlert
from .settings import read as read_settings

DIRECTIONS = {1: 'left', 2: 'right'}


class NavigationChime:
  def __init__(self, params):
    self.settings = read_settings(params)
    self._msgs = None
    self._last_fired = None

  def update(self, sm):
    if not self.settings.enabled or not self.settings.beep_enabled:
      return []
    if self._msgs is None:
      from openpilot.tesla.plugins import PluginMsgs
      self._msgs = PluginMsgs()
    now_ns = time.monotonic_ns()
    intent = self._msgs.fresh('lanes.intent').get('navassist') or {}
    delegated = intent.get('signalPurpose') == 'nativeLaneChange'
    if not (intent.get('valid') and intent.get('signalRequested')
            and (delegated or (intent.get('spLaneChangeReady') and intent.get('laneChangeAllowed')))):
      return []
    for service in ('modelV2', 'carState', 'carControl'):
      if not (sm.alive[service] and sm.valid[service]
              and 0 <= now_ns-sm.logMonoTime[service] <= 250_000_000):
        return []
    meta = sm['modelV2'].meta
    if meta.laneChangeState != log.LaneChangeState.laneChangeStarting:
      return []
    direction = DIRECTIONS.get(int(meta.laneChangeDirection))
    cs = sm['carState']
    physical = 'left' if cs.leftBlinker and not cs.rightBlinker else 'right' if cs.rightBlinker and not cs.leftBlinker else None
    if direction is None or direction != intent.get('direction') or physical != direction or not sm['carControl'].latActive:
      return []
    if getattr(cs, direction+'Blindspot'):
      return []
    key = tuple(intent.get(k) for k in ('sessionId', 'routeRevision', 'maneuverEventId', 'requestId')) + (direction,)
    if key == self._last_fired:
      return []
    self._last_fired = key
    return [PluginAlert('warning', 'Navigation turn signal', direction.capitalize())]


class NavigationBuzzerPolicy:
  """Restrict ordinary GPIO prompts while this navigation plugin is enabled.

  Emergency warnings and engagement changes are outside this policy's authority.
  """
  def __init__(self, params):
    self.params = params
    self._refresh_at = 0.
    self._enabled = False

  def allow_prompt(self, title, alert_type):
    now = time.monotonic()
    if now >= self._refresh_at:
      self._enabled = self.params.get_bool('ExtNavAssistEnabled')
      self._refresh_at = now + 1.
    return not self._enabled or (title == 'Navigation turn signal'
                                and alert_type == 'xpilotPluginWarning/permanent')
