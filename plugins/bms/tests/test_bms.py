"""P25: the bms plugin decodes 0x132/0x292 right (current sign, scales), drops stale and other-bus frames,
and publishes carStateSP.teslaBattery."""
import time
import types

from openpilot.cereal import custom

from ..plugin import HV_STATUS, SOC_STATUS, Bms, decode

# 400.00 V, current raw -1234 * -0.1 = 123.4 A discharging; SOC raw 765 at bit 10 = 76.5 %
HV = (40000 | ((-1234 & 0xFFFF) << 16)).to_bytes(8, "little")
SOC = (765 << 10).to_bytes(8, "little")
NOW = 10_000_000_000


def test_decode():
  got = decode({HV_STATUS: (NOW, HV), SOC_STATUS: (NOW, SOC)}, NOW)
  assert got is not None
  assert all(abs(a - b) <= 1e-6 for a, b in zip(got, (76.5, 400.0, 123.4), strict=True)), got


def test_decode_rejects_stale_frame():
  assert decode({HV_STATUS: (NOW - 3_000_000_000, HV), SOC_STATUS: (NOW, SOC)}, NOW) is None


def test_observe_and_publish():
  bms = Bms(types.SimpleNamespace(carFingerprint="x"), None)
  bms.observe_can([(NOW, [(HV_STATUS, HV, 0), (SOC_STATUS, SOC, 1)])], NOW)
  assert HV_STATUS not in bms.frames and SOC_STATUS in bms.frames, sorted(bms.frames)
  cs_sp = custom.CarStateSP.new_message()
  bms.publish_state(cs_sp)
  assert not cs_sp.teslaBattery.available
  bms.frames = {HV_STATUS: (time.monotonic_ns(), HV), SOC_STATUS: (time.monotonic_ns(), SOC)}
  bms.publish_state(cs_sp)
  assert cs_sp.teslaBattery.available and abs(cs_sp.teslaBattery.soc - 76.5) <= 1e-3, cs_sp.teslaBattery
