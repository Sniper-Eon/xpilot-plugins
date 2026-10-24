import pytest

from ..controller import AmbientLightingController


class FakeParams:
  values = {
    "TeslaBlindspotAmbientEnabled": True,
    "TeslaBlindspotAmbientDayBrightness": 100,
    "TeslaBlindspotAmbientBrightness": 30,
  }

  def get_bool(self, key):
    return bool(self.values.get(key, False))

  def get(self, key, return_default=False):
    return self.values.get(key)


@pytest.mark.parametrize("left,right,night,brightness", [(1, 0, False, 100), (0, 2, True, 30), (1, 2, True, 30)])
def test_blindspot_frame_is_bounded(left, right, night, brightness):
  c = AmbientLightingController()
  c.service_params(FakeParams())
  now = 10_000_000_000
  c.observe_frame(now, 0x679, bytes(7), 1)
  c.update_blindspot(left, right, night, now)
  frames = c.take_can_sends(now)
  assert len(frames) == 1
  frame = frames[0]
  assert frame.address == 0x679 and frame.src == 1 and len(frame.dat) == 7
  assert tuple(frame.dat[1:4]) == (255, 0, 0) and (frame.dat[4] & 127) == brightness
  assert c.take_can_sends(now + 1) == []
  c.update_blindspot(0, 0, night, now + 100_000_000)
  assert c.take_can_sends(now + 100_000_000) == []


def test_no_transmit_without_fresh_can():
  c = AmbientLightingController()
  c.service_params(FakeParams())
  c.update_blindspot(1, 1, True, 20_000_000_000)
  assert c.take_can_sends(20_000_000_000) == []
