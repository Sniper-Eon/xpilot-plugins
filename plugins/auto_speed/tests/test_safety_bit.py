"""setup() sets the panda param bit from the manifest (not a hard-coded value), only behind its vehicle/longitudinal gates."""
from types import SimpleNamespace

from opendbc.sunnypilot.car.tesla.values import TeslaFlagsSP

from ..plugin import AutoSpeed


def test_bit_from_manifest_and_gates():
  plugin = object.__new__(AutoSpeed)
  plugin.MANIFEST = SimpleNamespace(safety={"param_bit": "0x2000"})
  plugin.controller = SimpleNamespace(configured=False)
  for long, flags, bit in ((True, 0, 0), (True, TeslaFlagsSP.HAS_VEHICLE_BUS, 0x2000), (False, TeslaFlagsSP.HAS_VEHICLE_BUS, 0)):
    plugin.CP = SimpleNamespace(openpilotLongitudinalControl=long)
    cp_sp = SimpleNamespace(flags=flags, safetyParam=0)
    plugin.setup(cp_sp)
    assert cp_sp.safetyParam == bit, (long, flags)
