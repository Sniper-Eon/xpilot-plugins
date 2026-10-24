"""External compute plugin: runs externald, which bridges providers (tcp.py first; an LLM API client can follow)
to cereal externalIn/externalOut. It does not control the car: consumers are other plugins, which must check
freshness (provider.is_fresh) and go through their own hooks and limits. Params: XpilotExternal*.
Other plugins add providers through their own external_provider hook."""
import secrets

from openpilot.tesla.plugin import Plugin


def _always(started, params, CP) -> bool:
  return True


class ExternalCompute(Plugin):

  @classmethod
  def processes(cls) -> list:
    from openpilot.system.manager.process import PythonProcess
    return [PythonProcess("externald", f"{__package__}.externald", _always)]

  @classmethod
  def external_provider(cls, params):
    from .tcp import TcpProvider
    token = params.get("XpilotExternalToken")
    if not token:
      token = secrets.token_hex(8)
      params.put("XpilotExternalToken", token)
    return TcpProvider(token, port=int(params.get("XpilotExternalPort", return_default=True)))
