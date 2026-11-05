"""Local demo and DBC cross-check for the 0x238 decoder.

Run from the xpilot-plugins root (no car, no device):

  X=<xpilot checkout>
  PYTHONPATH=$X:$X/opendbc_repo python3 -m plugins.tesla_map.demo

It packs the frames with opendbc's CANPacker from tesla_modely_hw4_perception.dbc, so a wrong bit layout fails here
before the plugin ever runs on the car, then prints the tile lines and the Params snapshot for a few situations.
"""
from __future__ import annotations

import json

from opendbc.can import CANPacker

from .compare import CONFLICT_CONFIRM_NS, LimitComparator
from .decode import MPH_TO_MPS, KPH_TO_MPS, decode_frame
from .view import build_payload, tile_lines

DBC = "tesla_modely_hw4_perception"
MESSAGE = "UI_driverAssistMapData"
BUS = 1

CITY = {"UI_mapSpeedLimit": 13, "UI_mapSpeedLimitType": 1, "UI_mapSpeedUnits": 1, "UI_roadClass": 3,
        "UI_gpsRoadMatch": 1, "UI_navRouteActive": 1, "UI_nextBranchDist": 120, "UI_rejectRightLane": 1}
HIGHWAY = {"UI_mapSpeedLimit": 21, "UI_mapSpeedLimitType": 1, "UI_mapSpeedUnits": 1, "UI_roadClass": 1,
           "UI_controlledAccess": 1, "UI_gpsRoadMatch": 1, "UI_navRouteActive": 1, "UI_nextBranchDist": 250,
           "UI_nextBranchRightOffRamp": 1, "UI_rejectLeftLane": 1, "UI_rejectAutosteer": 1}
MISMATCH = {"UI_mapSpeedLimit": 13, "UI_mapSpeedLimitType": 1, "UI_mapSpeedUnits": 1, "UI_roadClass": 1,
            "UI_controlledAccess": 1, "UI_gpsRoadMatch": 1}
MILES = {"UI_mapSpeedLimit": 15, "UI_mapSpeedLimitType": 2, "UI_mapSpeedUnits": 0, "UI_roadClass": 2,
         "UI_gpsRoadMatch": 1}


def pack(packer: CANPacker, values: dict) -> bytes:
  _address, data, _bus = packer.make_can_msg(MESSAGE, BUS, values)
  return data


def show(packer: CANPacker, name: str, values: dict, sp_value: float) -> dict:
  """sp_value is the car's fused limit in the map frame's unit (km/h or mph)."""
  data = decode_frame(pack(packer, values))
  if data is None:
    raise SystemExit(f"{name}: decoder rejected an 8-byte frame")
  sp_mps = sp_value * (MPH_TO_MPS if data.unit == "mph" else KPH_TO_MPS) if sp_value else 0.0
  comparator = LimitComparator()
  trusted = data.regular and data.gps_match
  first = comparator.update(data.speed_limit, data.unit, sp_mps, 1_000_000_000, trusted=trusted)
  settled = comparator.update(data.speed_limit, data.unit, sp_mps, 1_000_000_000 + CONFLICT_CONFIRM_NS, trusted=trusted)
  payload = build_payload(data, settled, sp_mps)
  lines = tile_lines(payload)
  print(f"{name:9s} sp={sp_value:3.0f}{data.unit} cmp={first.state:9s}->{settled.state:9s} "
        f"conflict={settled.conflict}")
  print(f"          tile={lines}")
  return payload


def main() -> int:
  packer = CANPacker(DBC)
  print(f"{DBC} / {MESSAGE} / bus {BUS}\n")
  payload = show(packer, "city", CITY, 60)
  show(packer, "highway", HIGHWAY, 100)
  show(packer, "mismatch", MISMATCH, 75)
  show(packer, "miles", MILES, 70)
  print(f"\nno frame  tile={tile_lines(None)}")
  print("\nparams snapshot (city):")
  print(json.dumps(payload, indent=2, sort_keys=True))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
