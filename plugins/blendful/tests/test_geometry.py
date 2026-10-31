import math
from types import SimpleNamespace

from plugins.blendful.geometry import lane_center


class Line:
  def __init__(self, y):
    self.x = [0.0, 5.0, 10.0, 20.0, 40.0, 60.0]
    self.y = [y] * 6


def model(left=-1.8, right=1.8, lp=0.99, rp=0.99, ls=0.05, rs=0.05):
  return SimpleNamespace(
    laneLines=[Line(left - 3.6), Line(left), Line(right), Line(right + 3.6)],
    laneLineProbs=[0.99, lp, rp, 0.99],
    laneLineStds=[0.05, ls, rs, 0.05],
  )


def test_centered_lane_has_high_trust():
  center, trust = lane_center(model(), 10.0)
  assert abs(center) < 1e-6
  assert trust > 0.9


def test_asymmetric_real_lane_still_reaches_draw_gate():
  center, trust = lane_center(model(lp=0.78, rp=0.08, ls=0.14, rs=0.40), 5.0)
  assert abs(center) < 1e-6
  assert trust > 0.05


def test_wide_lane_is_rejected():
  assert lane_center(model(left=-3.0, right=3.0), 10.0) is None


def test_low_probability_has_low_trust():
  center, trust = lane_center(model(lp=0.1, rp=0.1), 10.0)
  assert abs(center) < 1e-6
  assert trust < 0.2
