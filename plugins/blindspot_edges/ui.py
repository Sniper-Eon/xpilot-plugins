"""Blind-spot edges: while a car is in the left/right blind spot, the left/right column gets a red gradient
(strong at the screen edge, faint toward the view), like mici's critical alert overlay."""
import pyray as rl

from openpilot.tesla.ui.plugin_ui import ScreenOverlay

RED = (255, 0, 21)  # mici AlertStatus.critical
OUTER, INNER = int(255 * 0.6), int(255 * 0.1)


class BlindspotEdges(ScreenOverlay):
  def __init__(self):
    self.left = self.right = False

  def update(self, sm) -> None:
    cs = sm['carState']
    self.left, self.right = cs.leftBlindspot, cs.rightBlindspot

  def draw(self, zones: dict) -> None:
    outer, inner = rl.Color(*RED, OUTER), rl.Color(*RED, INNER)
    if self.left:
      r = zones["left"]
      rl.draw_rectangle_gradient_h(int(r.x), int(r.y), int(r.width), int(r.height), outer, inner)
    if self.right:
      r = zones["right"]
      rl.draw_rectangle_gradient_h(int(r.x), int(r.y), int(r.width), int(r.height), inner, outer)
