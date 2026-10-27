"""Car status tile: cluster speed, gear, blinkers and blind spots, with the xpilot wordmark."""
import pyray as rl

from openpilot.common.constants import CV
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import gui_app
from openpilot.tesla.ui.tile import Tile
from openpilot.tesla.ui.tiles import TileSpec

_LOGO = None


def _logo():
  """The host's white xpilot wordmark, loaded once."""
  global _LOGO
  if _LOGO is None:
    _LOGO = gui_app.texture("icons_mici/xpilot_logo.png", 140, None)
  return _LOGO


class CarTile(Tile):
  SPEC = TileSpec("car", "Car", sizes=("small", "medium", "wide"), hz=10, order=50)

  def state(self, sm):
    cs = sm['carState']
    speed = cs.vEgoCluster * (CV.MS_TO_KPH if ui_state.is_metric else CV.MS_TO_MPH)
    blink = ("<" if cs.leftBlinker else " ") + (">" if cs.rightBlinker else " ")
    spots = ("L" if cs.leftBlindspot else "-") + ("R" if cs.rightBlindspot else "-")
    return f"{speed:.0f} {'km/h' if ui_state.is_metric else 'mph'}", f"{str(cs.gearShifter)[:1].upper()}  {blink}  {spots}"

  def draw(self, rect, size, state):
    self.draw_lines(rect, list(state))
    texture = _logo()
    rl.draw_texture(texture, int(rect.x + rect.width - texture.width - 16), int(rect.y + 16), rl.WHITE)
