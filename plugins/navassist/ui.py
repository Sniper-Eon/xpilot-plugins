"""Big-screen navigation overlay: next maneuver, lane guidance and Tesla's own ALC verdict.

The phone supplies navigation observations only; this widget never controls the car. It reads pluginMsg, so it
works with the same data the lane-change policy and speed ceiling consume."""
import pyray as rl

from openpilot.tesla.ui.plugin_ui import ScreenOverlay
from .display import read_state, guidance_visible, guidance_only, signal_status

WHITE = (255, 255, 255)
AMBER = (255, 176, 0)
RED = (235, 60, 60)
DIM = (150, 150, 150)


def _arrow(maneuver: str) -> str:
  return {
    "slight_left": "KEEP L", "slight_right": "KEEP R", "turn_left": "TURN L", "turn_right": "TURN R",
    "sharp_left": "SHARP L", "sharp_right": "SHARP R", "u_turn_left": "U-TURN L", "u_turn_right": "U-TURN R",
    "keep_left": "KEEP L", "keep_right": "KEEP R", "merge_left": "MERGE L", "merge_right": "MERGE R",
    "exit_left": "EXIT L", "exit_right": "EXIT R", "ramp_left": "RAMP L", "ramp_right": "RAMP R",
    "roundabout": "ROUNDABOUT", "destination": "DEST", "straight": "STRAIGHT",
  }.get(maneuver, "")


class NavAssistOverlay(ScreenOverlay):
  def __init__(self):
    self.nav = {}
    self.intent = {}
    self.oem = {}
    self.topology = {}
    self._msgs = None

  def _fresh(self) -> None:
    try:
      if self._msgs is None:
        from openpilot.tesla.plugins import PluginMsgs
        self._msgs = PluginMsgs()
      for attr, value in read_state(self._msgs).items():
        setattr(self, attr, value)
    except Exception:
      self.nav, self.intent, self.oem, self.topology = {}, {}, {}, {}

  def update(self, sm) -> None:
    self._fresh()

  def draw(self, zones: dict) -> None:
    nav = self.nav or {}
    intent = self.intent or {}
    if not guidance_visible(nav) and not intent.get("signalRequested"):
      return
    view = zones.get("view")
    x = int(view.x) if view is not None else 300
    y = int(view.y) - 74 if view is not None else 40
    if y < 8:
      y = 8
    width = 560
    rl.draw_rectangle(x, y, width, 66, rl.Color(0, 0, 0, 190))
    lines = []
    if guidance_visible(nav):
      maneuver = _arrow(str(nav.get("maneuver", "none")))
      distance = float(nav.get("distanceM", 0.0))
      if maneuver:
        lines.append((f"{maneuver}  {distance:.0f} m", WHITE))
      if guidance_only(nav):
        lines.append(("GUIDANCE ONLY", AMBER))
      total = int(nav.get("laneTotalCount", -1))
      lanes = nav.get("lanes") or []
      recommended = [int(lane["index"]) + 1 for lane in lanes if lane.get("recommended")]
      if recommended and total > 0:
        lines.append((f"LANE {'/'.join(str(i) for i in recommended)} OF {total}", WHITE))
    if intent.get("signalRequested"):
      direction = str(intent.get("direction", "none")).upper()
      lines.insert(0, (f"NAV SIGNAL {direction}", AMBER))
      lines.insert(1, (signal_status(intent), AMBER))
    oem = self.oem or {}
    if oem.get("leftExplicitBlock") or oem.get("rightExplicitBlock"):
      side = "L" if oem.get("leftExplicitBlock") else "R"
      lines.append((f"OEM VETO {side}", RED))
    elif oem.get("alcFresh"):
      lines.append((str(oem.get("alcName", "")), DIM))
    for i, (text, color) in enumerate(lines[:2]):
      rl.draw_text_ex(rl.get_font_default(), text, rl.Vector2(x + 14, y + 8 + i * 28), 26, 0, rl.Color(*color, 255))
