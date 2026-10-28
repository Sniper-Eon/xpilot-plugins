"""One host buzzer notice per CP-owned maneuver; settings are cached once a second."""
import time

from openpilot.tesla.plugin import PluginAlert
from .settings import read


class CPChime:
  def __init__(self, params):
    self.params = params
    self._msgs = None
    self.previous = None
    self._settings = None
    self._next = 0.0

  def _read(self):
    now = time.monotonic()
    if self._settings is None or now >= self._next:
      self._settings = read(self.params)
      self._next = now + 1.0
    return self._settings

  def update(self, sm):
    settings = self._read()
    if not settings.enabled or not settings.beep:
      return []
    if self._msgs is None:
      from openpilot.tesla.plugins import PluginMsgs
      self._msgs = PluginMsgs()
    d = self._msgs.fresh('lanes.intent').get('cp_nav') or {}
    if not (d.get('valid') is True and d.get('signalRequested') is True):
      return []
    key = (d.get('sessionId'), d.get('routeRevision'),
           d.get('maneuverEventId', d.get('requestId')), str(d.get('direction', 'none')))
    if key == self.previous:
      return []
    self.previous = key
    return [PluginAlert('warning', 'CP navigation signal', str(d.get('direction', 'none')).capitalize())]
