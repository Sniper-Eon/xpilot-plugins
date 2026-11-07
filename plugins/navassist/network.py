"""Start the source-compatible transports; pairing is allowed only offroad."""
import threading

from .discovery import NavAssistDiscoveryServer, DISCOVERY_PORT
from .identity import NavAssistDeviceIdentity, NavAssistPairingStore
from .server import NavAssistHTTPServer
from .udp import NavAssistUDPServer

LISTEN_PORT = 7766


class NavigationTransports:
  def __init__(self, store, params, is_offroad):
    self.pairing = NavAssistPairingStore(params)
    identity = NavAssistDeviceIdentity.load_or_create(params=params)
    self.servers = []
    self.threads = []
    try:
      udp = NavAssistUDPServer(('0.0.0.0', 4213), store)
      self.udp = udp
      self.geometry = udp.geometry
      self.servers.append(udp)
      self.http = NavAssistHTTPServer(('0.0.0.0', LISTEN_PORT), store, identity, self.pairing)
      self.servers.append(self.http)
      self.servers.append(NavAssistDiscoveryServer(('0.0.0.0', DISCOVERY_PORT), identity, self.pairing,
                                                 is_offroad=is_offroad))
      for server in self.servers:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.threads.append(thread)
    except Exception:
      self.close()
      raise

  def set_status_provider(self, provider):
    # 只给 HTTP 用：手机上行的 UDP ACK 有严格字段白名单，多一个字段整包会被丢弃。
    target = getattr(self, 'http', None)
    if target is not None:
      target.status_provider = provider

  def close(self):
    for index, server in enumerate(self.servers):
      if index < len(self.threads):
        server.shutdown()
      server.server_close()
    for thread in self.threads:
      thread.join(timeout=2)
