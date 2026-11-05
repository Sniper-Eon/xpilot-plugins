"""Plugin-owned modeld with Jetlink attach.

Runs openpilot's local modeld, but wraps ModelState so the small model is attached to Jetlink after it is
built. If the link is off, unavailable, or attach returns None, the wrapper stays the local model and the
four model messages are unchanged. Failure of the link must never remove the local model.
"""
from __future__ import annotations

import sys
from pathlib import Path

VENDOR = Path(__file__).resolve().parent / 'vendor'
PYPATH = Path(__file__).resolve().parent / 'pylib'
for p in (str(VENDOR), str(PYPATH)):
  if p not in sys.path:
    sys.path.insert(0, p)


def main() -> None:
  from openpilot.selfdrive.modeld import modeld as host
  import jetlink_plugin_adapter as adapter

  host.chestnut_present = lambda: False
  host.cable_connected = lambda: False
  adapter.prepare()

  base = host.ModelState

  class AttachedModelState(base):
    def __init__(self, cam_w, cam_h, *args, **kwargs):
      super().__init__(cam_w, cam_h, *args, **kwargs)
      self._jetlink_joined = None
      if not kwargs.get('chestnut', False):
        try:
          joined = adapter.attach(self, cam_w, cam_h)
        except Exception as e:
          from openpilot.common.swaglog import cloudlog
          cloudlog.exception('jetlink attach failed: %s', e)
          joined = None
        if joined is not None:
          self._jetlink_joined = joined

    def __getattr__(self, name):
      joined = self.__dict__.get('_jetlink_joined')
      if joined is not None:
        return getattr(joined, name)
      raise AttributeError(name)

  host.ModelState = AttachedModelState
  host.main()


if __name__ == '__main__':
  main()
