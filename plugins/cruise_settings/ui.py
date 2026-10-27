"""Big-screen tile and page for the cruise switches."""
from openpilot.tesla.plugins import PLUGINS
from openpilot.tesla.ui.pages.base import Header, ListPage, SettingRow, params
from openpilot.tesla.ui.tile import Tile
from openpilot.tesla.ui.tiles import TileSpec


def _plugin():
  return next(p for p in PLUGINS if p.NAME == 'cruise_settings')


class CruisePage(ListPage):
  def __init__(self):
    super().__init__()
    self.add(Header('CRUISE'))
    self.rows = [SettingRow(s) for s in _plugin().SETTINGS]
    self.add(*[r.item for r in self.rows])

  def refresh(self):
    for row in self.rows:
      row.refresh()


class CruiseTile(Tile):
  SPEC = TileSpec('cruise_settings', 'CRUISE', sizes=('small',), services=(), show='always', hz=2)
  PAGE = CruisePage

  def state(self, sm):
    p = params()
    icbm = bool(p.get_bool('ExtCruiseIcbm'))
    speed = str(p.get('ExtCruiseInitialSpeed', return_default=True) or '40')
    return (icbm, speed)

  def draw(self, rect, size, state):
    icbm, speed = state if state else (False, '--')
    self.draw_value(rect, f'{speed}' if icbm else 'OFF', 'km/h')
