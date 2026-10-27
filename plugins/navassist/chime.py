"""One audible preparation notice per valid navigation-owned signal request."""
from openpilot.tesla.plugin import PluginAlert
from .settings import read as read_settings


class NavigationChime:
  def __init__(self, params):
    self.settings = read_settings(params)
    self._msgs = None
    self._last_request = None

  def update(self, sm):
    if not self.settings.enabled or not self.settings.beep_enabled:
      return []
    if self._msgs is None:
      from openpilot.tesla.plugins import PluginMsgs
      self._msgs = PluginMsgs()
    intent = self._msgs.fresh('lanes.intent').get('navassist') or {}
    if not (intent.get('valid') and intent.get('signalRequested')
            and intent.get('direction') in ('left', 'right')):
      return []
    request = tuple(intent.get(k) for k in ('sessionId', 'routeRevision', 'maneuverEventId', 'requestId'))
    if request == self._last_request:
      return []
    self._last_request = request
    return [PluginAlert('warning', 'Navigation turn signal', intent['direction'].capitalize())]
