from types import SimpleNamespace

from openpilot.cereal import log

from plugins.blendful.control import BlendfulCorrection
from plugins.blendful.tests.test_geometry import model


class Params:
  def __init__(self, enabled=True):
    self.enabled = enabled

  def get_bool(self, key):
    return self.enabled


def sm(model_v2):
  return {"modelV2": model_v2}


def test_correction_pulls_toward_center():
  m = model()
  m.meta = SimpleNamespace(laneChangeState=log.LaneChangeState.off)
  m.position = SimpleNamespace(x=[0.0, 5.0, 10.0, 20.0, 40.0, 60.0], y=[0.5] * 6)
  c = BlendfulCorrection(Params())
  out = None
  for _ in range(20):
    out = c.update(sm(m), 10.0, 0.0)
  assert out is not None and out < 0.0


def test_disabled_returns_none():
  m = model()
  m.meta = SimpleNamespace(laneChangeState=log.LaneChangeState.off)
  m.position = SimpleNamespace(x=[0.0, 5.0, 10.0, 20.0, 40.0, 60.0], y=[0.5] * 6)
  assert BlendfulCorrection(Params(False)).update(sm(m), 10.0, 0.0) is None


def test_lane_change_blocks_correction():
  m = model()
  m.meta = SimpleNamespace(laneChangeState=log.LaneChangeState.laneChangeStarting)
  m.position = SimpleNamespace(x=[0.0, 5.0, 10.0, 20.0, 40.0, 60.0], y=[0.5] * 6)
  assert BlendfulCorrection(Params()).update(sm(m), 10.0, 0.0) is None
