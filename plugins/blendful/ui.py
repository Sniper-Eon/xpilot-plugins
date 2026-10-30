"""Blue Blendful lane-center line drawn on the mici road view."""
from __future__ import annotations

import numpy as np
import pyray as rl
from openpilot.cereal import log
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.shader_polygon import draw_polygon
from openpilot.tesla import plugins
from openpilot.tesla.ui.plugin_ui import RoadOverlay

from .geometry import lane_center

BLENDFUL_COLOR = (0, 200, 255)


class BlendfulRoadOverlay(RoadOverlay):
  def __init__(self):
    self._center = None
    self._trust = 0.0
    self._params = plugins.view(ui_state.params)

  def update(self, sm) -> None:
    self._center = None
    self._trust = 0.0
    if not self._params.get_bool('ExtBlendfulShowLine'):
      return
    try:
      model = sm['modelV2']
      if model.meta.laneChangeState != log.LaneChangeState.off:
        return
      result = lane_center(model, float(sm['carState'].vEgo))
    except (KeyError, AttributeError, TypeError):
      return
    if result is not None:
      self._center, self._trust = result

  def draw(self, road) -> None:
    if self._center is None or self._trust < 0.05:
      return
    points = road.lane_points()
    if len(points) < 3:
      return
    left, right = np.asarray(points[1][:, 1]), np.asarray(points[2][:, 1])
    if left.size == 0 or left.shape != right.shape:
      return
    center = np.asarray(points[1]).copy()
    center[:, 1] = (left + right) / 2.0
    poly = road.polygon(center, 0.15)
    if poly.size:
      draw_polygon(road.rect, poly, color=rl.Color(*BLENDFUL_COLOR, int(255 * self._trust)))
