"""Blendful lane-center plugin. Control and road overlay live in separate modules."""
from openpilot.tesla.plugin import Plugin


class BlendfulPlugin(Plugin):
  @classmethod
  def lat_correction(cls, CP, params):
    from .control import BlendfulCorrection
    return BlendfulCorrection(params)
