"""Jetlink accelerator plugin.

Owns role:perception.model while enabled. jet_modeld runs the local model and attaches Jetlink; jetlinkd
holds the USB gadget offroad and onroad so the Mac can connect before ignition.
"""
from openpilot.tesla.plugin import Plugin


def _always(started, params, CP) -> bool:
  return True


def _onroad(started, params, CP) -> bool:
  return started


class Jetlink(Plugin):

  @classmethod
  def processes(cls) -> list:
    from openpilot.system.manager.process import PythonProcess
    return [
      PythonProcess("jet_modeld", f"{__package__}.modeld", _onroad),
      PythonProcess("jetlinkd", f"{__package__}.jetlinkd", _always),
    ]
