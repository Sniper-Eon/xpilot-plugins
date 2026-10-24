"""setup() sets the panda param bit from the manifest (not a hard-coded value), only with the vehicle bus."""
from types import SimpleNamespace

from opendbc.sunnypilot.car.tesla.values import TeslaFlagsSP

from ..plugin import AmbientLight


def test_bit_from_manifest_and_gate():
  plugin = object.__new__(AmbientLight)
  plugin.MANIFEST = SimpleNamespace(safety={"param_bit": "0x4000"})
  for flags, bit in ((0, 0), (TeslaFlagsSP.HAS_VEHICLE_BUS, 0x4000)):
    cp_sp = SimpleNamespace(flags=flags, safetyParam=0)
    plugin.setup(cp_sp)
    assert cp_sp.safetyParam == bit, flags
