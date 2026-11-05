"""Tile: Tesla's own map data from 0x238 (map limit, road class, next branch, lane rejects).

Display only. The card plugin in plugin.py decodes the frame and publishes ExtTeslaMapState; this tile polls it twice a
second and shows the ASCII lines from view.tile_lines(). A missing or stale frame reads "MAP SNA".
"""
from __future__ import annotations

import json

from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.tesla import plugins
from openpilot.tesla.ui.tile import Tile
from openpilot.tesla.ui.tiles import TileSpec
from .view import tile_lines


class TeslaMapTile(Tile):
  SPEC = TileSpec("tesla_map", "Tesla Map", sizes=("small", "medium", "wide"), show="onroad", hz=2, order=70)

  def __init__(self):
    self._params = None

  def _payload(self) -> dict | None:
    if self._params is None:
      self._params = plugins.view(ui_state.params)
    try:
      payload = self._params.get("ExtTeslaMapState", return_default=True)
    except (TypeError, ValueError, KeyError):
      return None
    if isinstance(payload, str):
      try:
        payload = json.loads(payload)
      except ValueError:
        return None
    return payload if isinstance(payload, dict) else None

  def state(self, sm):
    return tile_lines(self._payload())

  def draw(self, rect, size, state):
    self.draw_lines(rect, list(state), size=34)
