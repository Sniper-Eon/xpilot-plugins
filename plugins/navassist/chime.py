"""One audible notice when the navigation-requested lane change actually starts.

Requires a fresh matching navigation request, physical lamp and actual SP
laneChangeStarting; a blinker that is never executed stays silent.
"""
import time

from openpilot.cereal import log
from openpilot.tesla.plugin import PluginAlert
from .settings import read as read_settings

DIRECTIONS = {1: 'left', 2: 'right'}
START_FALLBACK_NS = 1_200_000_000   # 打灯后多久仍未见模型确认就用自判补提示音


class NavigationChime:
  def __init__(self, params):
    self.settings = read_settings(params)
    self._msgs = None
    self._last_fired = None
    self._armed = None

  def update(self, sm):
    if not self.settings.enabled or not self.settings.beep_enabled:
      return []
    if self._msgs is None:
      from openpilot.tesla.plugins import PluginMsgs
      self._msgs = PluginMsgs()
    now_ns = time.monotonic_ns()
    intent = self._msgs.fresh('lanes.intent').get('navassist') or {}
    delegated = intent.get('signalPurpose') == 'nativeLaneChange'
    gate = bool(intent.get('valid') and intent.get('signalRequested')
                and (delegated or (intent.get('spLaneChangeReady') and intent.get('laneChangeAllowed'))))
    direction = intent.get('direction')
    if gate and direction in ('left', 'right'):
      key = tuple(intent.get(k) for k in ('sessionId', 'routeRevision', 'maneuverEventId', 'requestId')) + (direction,)
      self._armed = (key, direction, intent.get('sessionId'), intent.get('routeRevision'), now_ns)
    for service in ('modelV2', 'carState', 'carControl'):
      if not (sm.alive[service] and sm.valid[service]
              and 0 <= now_ns-sm.logMonoTime[service] <= 250_000_000):
        return []
    meta = sm['modelV2'].meta
    # capnp returns DynamicEnum here; int()/enum == raises TypeError and faults the hook every frame.
    try:
      lane_state = str(getattr(meta, 'laneChangeState', 'off')).split('.')[-1]
      direction_text = str(getattr(meta, 'laneChangeDirection', 'none')).lower()
    except Exception:
      return []
    if lane_state != 'laneChangeStarting':
      # 模型没报「开始变道」时，退回到我们自己的请求：灯已亮、横向已激活、
      # 请求已发出 1.2 秒仍无模型确认，就补一声，避免大部分变道没有提示音。
      return self._start_fallback(intent, sm, now_ns)
    model_direction = 'left' if 'left' in direction_text else 'right' if 'right' in direction_text else None
    cs = sm['carState']
    physical = 'left' if cs.leftBlinker and not cs.rightBlinker else 'right' if cs.rightBlinker and not cs.leftBlinker else None
    if model_direction is None or physical != model_direction or not sm['carControl'].latActive:
      return []
    if getattr(cs, model_direction+'Blindspot'):
      return []
    key = None
    if gate and direction == model_direction:
      key = tuple(intent.get(k) for k in ('sessionId', 'routeRevision', 'maneuverEventId', 'requestId')) + (model_direction,)
    elif self._armed is not None:
      armed_key, armed_direction, armed_session, armed_revision, armed_ns = self._armed
      same_scope = (intent.get('sessionId') == armed_session and intent.get('routeRevision') == armed_revision)
      if armed_direction == model_direction and same_scope and 0 <= now_ns - armed_ns <= 2_000_000_000:
        key = armed_key
    if key is None or key == self._last_fired:
      return []
    self._last_fired = key
    self._armed = None
    return [PluginAlert('warning', 'Navigation turn signal', model_direction.capitalize())]


  def _start_fallback(self, intent, sm, now_ns):
    if self._armed is None or not self.settings.beep_enabled:
      return []
    armed_key, armed_direction, armed_session, armed_revision, armed_ns = self._armed
    if armed_direction not in ('left', 'right'):
      return []
    if now_ns - armed_ns < START_FALLBACK_NS:
      return []
    if intent.get('sessionId') != armed_session or intent.get('routeRevision') != armed_revision:
      return []
    cs = sm['carState']
    physical = 'left' if cs.leftBlinker and not cs.rightBlinker else 'right' if cs.rightBlinker and not cs.leftBlinker else None
    if physical != armed_direction:
      return []
    if not sm['carControl'].latActive:
      return []
    if getattr(cs, armed_direction + 'Blindspot'):
      return []
    if armed_key == self._last_fired:
      return []
    self._last_fired = armed_key
    self._armed = None
    return [PluginAlert('warning', 'Navigation lane change', armed_direction.capitalize())]


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
