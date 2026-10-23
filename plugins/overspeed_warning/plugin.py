"""Overspeed Warning: an example xpilot plugin (alerts category, store-installed)."""
from openpilot.tesla.plugin import Plugin, PluginAlert

from .logic import overspeed_kph


class _Source:
  def __init__(self, params):
    self.margin = float(params.get("ExtOverspeedMargin", return_default=True) or 0)  # read once per drive

  def update(self, sm) -> list:
    limit = sm['longitudinalPlanSP'].speedLimit.resolver.speedLimit
    over = overspeed_kph(sm['carState'].vEgo, limit, self.margin)
    return [PluginAlert("warning", f"{over} km/h over the speed limit")] if over is not None else []


class OverspeedWarning(Plugin):
  SERVICES = ("carState",)  # selfdrived reads carState on its own socket, not through sm

  @classmethod
  def alert_source(cls, CP, params):
    return _Source(params)
