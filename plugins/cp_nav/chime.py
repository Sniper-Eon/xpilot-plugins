"""One host buzzer notice per CP-owned lamp request; no phone authority."""
from openpilot.tesla.plugin import PluginAlert
from .settings import read


class CPChime:
  def __init__(self,params):self.params=params;self._msgs=None;self.previous=None
  def update(self,sm):
    settings=read(self.params)
    if not settings.enabled or not settings.beep:return []
    if self._msgs is None:
      from openpilot.tesla.plugins import PluginMsgs
      self._msgs=PluginMsgs()
    d=self._msgs.fresh('lanes.intent').get('cp_nav') or {}
    if not (d.get('valid') is True and d.get('signalRequested') is True):return []
    request=tuple(d.get(k) for k in ('sessionId','routeRevision','requestId'))
    if request==self.previous:return []
    self.previous=request
    return [PluginAlert('warning','CP navigation signal',str(d.get('direction','none')).capitalize())]
