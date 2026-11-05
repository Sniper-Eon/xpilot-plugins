"""0x238 UI_driverAssistMapData: every signal decodes from the DBC packing, plus the sentinel and unit rules.

The frames are packed with opendbc's CANPacker from tesla_modely_hw4_perception.dbc, so this also cross-checks the
hand-written bit offsets against the DBC every run.
"""
import pytest
from opendbc.can import CANPacker

from ..decode import STALE_NS, decode_frame, is_fresh
from ..demo import DBC, pack

PACKER = CANPacker(DBC)

ALL_SIGNALS = {
  "UI_mapSpeedLimitDependency": 2, "UI_roadClass": 5, "UI_inSuperchargerGeofence": 1, "UI_mapSpeedUnits": 1,
  "UI_mapSpeedLimit": 17, "UI_mapSpeedLimitType": 3, "UI_countryCode": 44, "UI_streetCount": 2,
  "UI_gpsRoadMatch": 1, "UI_navRouteActive": 1, "UI_parallelAutoparkEnabled": 1,
  "UI_perpendicularAutoparkEnabled": 0, "UI_nextBranchDist": 240, "UI_controlledAccess": 1,
  "UI_nextBranchLeftOffRamp": 0, "UI_nextBranchRightOffRamp": 1, "UI_rejectLeftLane": 1,
  "UI_rejectRightLane": 0, "UI_rejectHPP": 0, "UI_rejectNav": 1, "UI_rejectLeftFreeSpace": 1,
  "UI_rejectRightFreeSpace": 0, "UI_rejectAutosteer": 1, "UI_rejectHandsOn": 0,
  "UI_acceptBottsDots": 1, "UI_autosteerRestricted": 1, "UI_pmmEnabled": 0, "UI_scaEnabled": 1,
}


def frame(**values):
  return decode_frame(pack(PACKER, values))


def test_every_signal_decodes():
  d = frame(**ALL_SIGNALS)
  assert d is not None
  assert (d.dependency, d.road_class, d.supercharger, d.units) == (2, 5, True, 1)
  assert (d.speed_code, d.speed_limit, d.speed_type, d.limit_type) == (17, 80, 3, "DEPENDENT")
  assert (d.country_code, d.street_count, d.gps_match) == (44, 2, True)
  assert (d.nav_active, d.parallel_autopark, d.perpendicular_autopark) == (True, True, False)
  assert (d.branch_raw, d.branch_distance_m, d.controlled_access) == (24, 240, True)
  assert (d.branch_left_ramp, d.branch_right_ramp, d.branch_side) == (False, True, "R")
  assert (d.reject_left, d.reject_right, d.reject_hpp, d.reject_nav) == (True, False, False, True)
  assert (d.reject_left_free, d.reject_right_free) == (True, False)
  assert (d.reject_autosteer, d.reject_hands_on) == (True, False)
  assert (d.accept_botts, d.autosteer_restricted, d.pmm, d.sca) == (True, True, False, True)
  assert (d.unit, d.limit_known, d.unlimited, d.regular) == ("kph", True, False, False)
  assert d.reject_labels == ("L", "LF", "AS")
  assert d.dependency_label == "RAIN" and d.road_label == "C5"
  assert d.speed_limit_mps == pytest.approx(80 / 3.6)


def test_mph_units_convert_to_mps():
  d = frame(**{"UI_mapSpeedLimit": 13, "UI_mapSpeedLimitType": 1, "UI_mapSpeedUnits": 0})
  assert (d.unit, d.speed_limit) == ("mph", 60)
  assert d.speed_limit_mps == pytest.approx(60 * 0.44704)


def test_unlimited_and_sna_codes():
  unlimited = frame(**{"UI_mapSpeedLimit": 30, "UI_mapSpeedLimitType": 1})
  assert unlimited.speed_limit is None and unlimited.unlimited and not unlimited.limit_known
  assert unlimited.speed_limit_mps is None
  sna = frame(**{"UI_mapSpeedLimit": 31, "UI_mapSpeedLimitType": 7})
  assert sna.speed_limit is None and not sna.unlimited and sna.limit_type == "SNA"
  unknown = frame(**{"UI_mapSpeedLimit": 0})
  assert unknown.speed_limit is None and not unknown.unlimited


def test_branch_distance_sentinel():
  assert frame(**{"UI_nextBranchDist": 0}).branch_distance_m == 0
  assert frame(**{"UI_nextBranchDist": 120}).branch_distance_m == 120
  # raw 31 is SNA, not a 310 m distance
  assert frame(**{"UI_nextBranchDist": 310}).branch_distance_m is None


def test_regular_is_the_only_comparable_type():
  assert frame(**{"UI_mapSpeedLimit": 13, "UI_mapSpeedLimitType": 1}).regular
  assert not frame(**{"UI_mapSpeedLimit": 13, "UI_mapSpeedLimitType": 2}).regular
  assert not frame(**{"UI_mapSpeedLimit": 13, "UI_mapSpeedLimitType": 4}).regular


def test_wrong_length_is_rejected():
  assert decode_frame(b"\x00" * 7) is None
  assert decode_frame(b"") is None
  assert decode_frame(None) is None
  assert decode_frame(bytearray(8)) is not None


def test_staleness_window():
  assert is_fresh(0, 0)
  assert is_fresh(0, STALE_NS)
  assert not is_fresh(0, STALE_NS + 1)
  assert not is_fresh(10, 9)
