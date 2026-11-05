"""The published snapshot and the tile text: JSON-safe, ASCII-only, sane when data is missing."""
import json

from opendbc.can import CANPacker

from ..compare import CONFLICT_CONFIRM_NS, LimitComparator
from ..decode import decode_frame
from ..demo import DBC, pack
from ..view import build_payload, tile_lines

PACKER = CANPacker(DBC)
KPH = 1 / 3.6


def payload(values, sp_value=60.0):
  data = decode_frame(pack(PACKER, {"UI_mapSpeedUnits": 1, **values}))
  assert data is not None
  sp_mps = sp_value * KPH
  comparison = LimitComparator().update(data.speed_limit, data.unit, sp_mps, 0,
                                        trusted=data.regular and data.gps_match)
  return data, build_payload(data, comparison, sp_mps)


def test_payload_is_json_safe_and_complete():
  data, snapshot = payload({"UI_mapSpeedLimit": 13, "UI_mapSpeedLimitType": 1, "UI_navRouteActive": 1,
                            "UI_nextBranchDist": 120, "UI_gpsRoadMatch": 1})
  assert json.loads(json.dumps(snapshot)) == snapshot
  assert snapshot["fresh"] and snapshot["v"] == 1
  assert snapshot["limit"] == {"code": 13, "value": 60, "unit": "kph", "type": "REGULAR",
                               "unlimited": False, "regular": True}
  assert snapshot["nav"] == {"active": True, "branch_m": 120, "side": "", "left_ramp": False, "right_ramp": False}
  assert snapshot["cmp"]["state"] == "AGREE"
  assert tile_lines(snapshot) == ("MAP 60", "EXIT 120", "SP 60 OK"), "an SNA road class is omitted, not printed"


def test_highway_tile_has_road_and_exit():
  _data, snapshot = payload({"UI_mapSpeedLimit": 21, "UI_mapSpeedLimitType": 1, "UI_roadClass": 1,
                             "UI_controlledAccess": 1, "UI_navRouteActive": 1, "UI_nextBranchDist": 250,
                             "UI_nextBranchRightOffRamp": 1, "UI_rejectLeftLane": 1}, sp_value=100)
  assert tile_lines(snapshot) == ("MAP 100", "HWY C1 EXIT 250 R", "SP 100 OK", "REJ L")


def test_conflict_marks_the_limit_line():
  data = decode_frame(pack(PACKER, {"UI_mapSpeedLimit": 13, "UI_mapSpeedLimitType": 1, "UI_roadClass": 1,
                                    "UI_mapSpeedUnits": 1, "UI_gpsRoadMatch": 1}))
  comparator = LimitComparator()
  comparator.update(data.speed_limit, data.unit, 75 * KPH, 0)
  settled = comparator.update(data.speed_limit, data.unit, 75 * KPH, CONFLICT_CONFIRM_NS)
  snapshot = build_payload(data, settled, 75 * KPH)
  assert tile_lines(snapshot)[0] == "MAP 60 !"
  assert tile_lines(snapshot)[2] == "SP 75 -15"


def test_unlimited_advisory_and_unknown_limits():
  _, unlimited = payload({"UI_mapSpeedLimit": 30, "UI_mapSpeedLimitType": 1})
  _, advisory = payload({"UI_mapSpeedLimit": 13, "UI_mapSpeedLimitType": 2})
  _, unknown = payload({"UI_mapSpeedLimit": 0})
  assert tile_lines(unlimited)[0] == "MAP UNL"
  assert tile_lines(advisory)[0] == "MAP 60 ADV"
  assert tile_lines(unknown)[0] == "MAP --"


def test_missing_or_stale_snapshot():
  assert tile_lines(None) == ("MAP SNA",)
  assert tile_lines({}) == ("MAP SNA",)
  assert tile_lines({"fresh": False}) == ("MAP SNA",)


def test_unlimited_map_with_a_fused_limit_is_not_no_map():
  _data, snapshot = payload({"UI_mapSpeedLimit": 30, "UI_mapSpeedLimitType": 1}, sp_value=130)
  assert tile_lines(snapshot) == ("MAP UNL", "SP 130")


def test_branch_at_zero_reads_now():
  _data, snapshot = payload({"UI_mapSpeedLimit": 13, "UI_mapSpeedLimitType": 1, "UI_navRouteActive": 1,
                             "UI_nextBranchDist": 0, "UI_nextBranchRightOffRamp": 1})
  assert tile_lines(snapshot)[1] == "EXIT NOW R"


def test_no_sp_limit_text():
  data = decode_frame(pack(PACKER, {"UI_mapSpeedLimit": 13, "UI_mapSpeedLimitType": 1}))
  comparison = LimitComparator().update(data.speed_limit, data.unit, 0.0, 0)
  lines = tile_lines(build_payload(data, comparison, 0.0))
  assert "MAP ONLY" in lines


def test_tile_lines_are_ascii():
  for values in ({"UI_mapSpeedLimit": 13, "UI_navRouteActive": 1, "UI_nextBranchDist": 120,
                  "UI_rejectLeftLane": 1, "UI_rejectRightLane": 1, "UI_mapSpeedLimitType": 2},
                 {"UI_mapSpeedLimit": 30, "UI_controlledAccess": 1, "UI_roadClass": 1}):
    _data, snapshot = payload(values)
    for line in tile_lines(snapshot):
      assert line.isascii(), line
