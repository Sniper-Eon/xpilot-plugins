"""Card plugin: vehicle-bus only, throttled snapshot, stale handling, and a params failure never drops the plugin."""
import types

from opendbc.can import CANPacker

from ..decode import MAP_ADDRESS, STALE_NS
from ..demo import DBC, pack
from ..plugin import STATE_PARAM, WRITE_INTERVAL_NS, TeslaMap

PACKER = CANPacker(DBC)
KPH = 1 / 3.6
T0 = 1_000_000_000


def frame(**values):
  return pack(PACKER, values)


def city(code=13):
  return frame(**{"UI_mapSpeedLimit": code, "UI_mapSpeedLimitType": 1, "UI_mapSpeedUnits": 1,
                  "UI_roadClass": 3, "UI_gpsRoadMatch": 1})


class FakeParams:
  def __init__(self, failing=False):
    self.values, self.writes, self.failing = {}, [], failing

  def get(self, key, block=False, return_default=False):
    return self.values.get(key)

  def get_bool(self, key, block=False):
    return bool(self.values.get(key, False))

  def put(self, key, value, block=False):
    if self.failing:
      raise KeyError(key)
    self.values[key] = value
    self.writes.append((key, value))


def make_plugin(params=None):
  plugin = TeslaMap(types.SimpleNamespace(carFingerprint="TESLA_MODEL_Y"), params or FakeParams())
  clock = [T0]
  plugin._now_ns = lambda: clock[0]
  return plugin, clock


def cs(speed_kph):
  return types.SimpleNamespace(speedLimit=speed_kph * KPH)


def test_only_the_vehicle_bus_is_map_data():
  plugin, clock = make_plugin()
  plugin.observe_can([(T0, [(MAP_ADDRESS, city(), 2)])], T0)  # STW_ACTN_RQ on the autopilot-party bus
  assert plugin.data is None
  plugin.observe_can([(T0, [(MAP_ADDRESS, city(), 1)])], T0)
  assert plugin.data is not None


def test_short_and_foreign_frames_are_ignored():
  plugin, _clock = make_plugin()
  plugin.observe_can([(T0, [(MAP_ADDRESS, city()[:7], 1), (0x3C2, city(), 1)])], T0)
  assert plugin.data is None


def test_publishes_a_fresh_snapshot():
  params = FakeParams()
  plugin, _clock = make_plugin(params)
  plugin.observe_can([(T0, [(MAP_ADDRESS, city(), 1)])], T0)
  plugin.publish_state(cs(60))
  assert len(params.writes) == 1 and params.writes[0][0] == STATE_PARAM
  payload = params.values[STATE_PARAM]
  assert payload["fresh"] and payload["limit"]["value"] == 60 and payload["road"]["label"] == "C3"
  assert payload["cmp"]["state"] == "AGREE"


def test_writes_are_throttled_and_deduplicated():
  params = FakeParams()
  plugin, clock = make_plugin(params)
  plugin.observe_can([(T0, [(MAP_ADDRESS, city(), 1)])], T0)
  plugin.publish_state(cs(60))
  assert len(params.writes) == 1

  clock[0] = T0 + WRITE_INTERVAL_NS // 5
  plugin.observe_can([(clock[0], [(MAP_ADDRESS, city(21), 1)])], clock[0])  # code 21 = 100 km/h
  plugin.publish_state(cs(100))
  assert len(params.writes) == 1, "a change inside the interval waits"

  clock[0] = T0 + WRITE_INTERVAL_NS + 1
  plugin.publish_state(cs(100))
  assert len(params.writes) == 2 and params.values[STATE_PARAM]["limit"]["value"] == 100

  clock[0] += WRITE_INTERVAL_NS * 2  # same frame, same limits: nothing new to publish
  plugin.publish_state(cs(100))
  assert len(params.writes) == 2


def test_stale_frame_publishes_unavailable():
  params = FakeParams()
  plugin, clock = make_plugin(params)
  plugin.observe_can([(T0, [(MAP_ADDRESS, city(), 1)])], T0)
  plugin.publish_state(cs(60))
  clock[0] = T0 + STALE_NS + 1
  plugin.publish_state(cs(60))
  assert len(params.writes) == 2 and not params.values[STATE_PARAM]["fresh"]
  assert params.values[STATE_PARAM]["limit"] is None


def test_params_failure_does_not_raise_and_recovers():
  params = FakeParams(failing=True)
  plugin, clock = make_plugin(params)
  plugin.observe_can([(T0, [(MAP_ADDRESS, city(), 1)])], T0)
  plugin.publish_state(cs(60))  # put raises, publish_state must swallow it
  assert not params.writes

  params.failing = False
  clock[0] = T0 + WRITE_INTERVAL_NS + 1
  plugin.publish_state(cs(60))
  assert len(params.writes) == 1


def test_publish_without_car_state_does_not_raise():
  params = FakeParams()
  plugin, _clock = make_plugin(params)
  plugin.observe_can([(T0, [(MAP_ADDRESS, city(), 1)])], T0)
  plugin.publish_state(None)
  assert params.values[STATE_PARAM]["cmp"]["state"] == "MAP_ONLY"
