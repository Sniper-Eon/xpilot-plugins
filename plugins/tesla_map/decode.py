"""Decode Tesla's 0x238 ``UI_driverAssistMapData`` from the vehicle bus. Stdlib only, read-only.

Layout: opendbc ``tesla_modely_hw4_perception.dbc``, ``BO_ 568 UI_driverAssistMapData`` (8 bytes, Intel / @1+).
Enumerations: tesLAX Model 3 DBC ``VAL_ 568 UI_mapSpeedLimit`` -- codes are *upper bounds* ("LESS_OR_EQ_60"),
30 = unlimited, 31 = SNA. The limit is expressed in ``UI_mapSpeedUnits`` (0 mph, 1 kph), not in m/s.

This frame is not the right scroll wheel. 0x238 on the autopilot-party bus (source 2) is ``STW_ACTN_RQ``; only the
vehicle-bus frame (source 1) carries map data, which is why the card plugin filters on both address and bus.
"""
from __future__ import annotations

from dataclasses import dataclass

MAP_ADDRESS = 0x238
VEHICLE_BUS = 1  # opendbc CANBUS.vehicle; kept here so the decoder stays stdlib-only

# A 1 Hz frame is the norm; 5 s tolerates a couple of missed cycles before the tile says SNA.
STALE_NS = 5_000_000_000

MPH_TO_MPS = 0.44704
KPH_TO_MPS = 1.0 / 3.6

# UI_mapSpeedLimit code -> limit in UI_mapSpeedUnits (tesLAX DBC VAL_ 568: LESS_OR_EQ_5 .. LESS_OR_EQ_160).
SPEED_LIMIT = {
  1: 5, 2: 7, 3: 10, 4: 15, 5: 20, 6: 25, 7: 30, 8: 35, 9: 40, 10: 45,
  11: 50, 12: 55, 13: 60, 14: 65, 15: 70, 16: 75, 17: 80, 18: 85, 19: 90, 20: 95,
  21: 100, 22: 105, 23: 110, 24: 115, 25: 120, 26: 130, 27: 140, 28: 150, 29: 160,
}
LIMIT_UNKNOWN = 0
LIMIT_UNLIMITED = 30
LIMIT_SNA = 31

SPEED_TYPE = {1: "REGULAR", 2: "ADVISORY", 3: "DEPENDENT", 4: "BUMPS", 7: "SNA"}
ROAD_CLASS = {0: "SNA", 1: "C1", 2: "C2", 3: "C3", 4: "C4", 5: "C5", 6: "C6"}
DEPENDENCY = {0: "NONE", 1: "SCHOOL", 2: "RAIN", 3: "SNOW", 4: "TIME", 5: "SEASON", 6: "LANE", 7: "SNA"}
UNITS = {0: "mph", 1: "kph"}

# UI_nextBranchDist is 5 bits with factor 10; 31 is the SNA sentinel, so 0..300 m are real distances.
BRANCH_SNA = 31
BRANCH_STEP_M = 10


def _bits(value: int, start: int, size: int) -> int:
  return (value >> start) & ((1 << size) - 1)


@dataclass(frozen=True)
class MapData:
  """One decoded 0x238 frame. Field names follow the DBC signals."""
  dependency: int
  road_class: int
  supercharger: bool
  units: int
  speed_code: int
  speed_type: int
  country_code: int
  street_count: int
  gps_match: bool
  nav_active: bool
  parallel_autopark: bool
  perpendicular_autopark: bool
  branch_raw: int
  controlled_access: bool
  branch_left_ramp: bool
  branch_right_ramp: bool
  reject_left: bool
  reject_right: bool
  reject_hpp: bool
  reject_nav: bool
  reject_left_free: bool
  reject_right_free: bool
  reject_autosteer: bool
  reject_hands_on: bool
  accept_botts: bool
  autosteer_restricted: bool
  pmm: bool
  sca: bool

  @property
  def unit(self) -> str:
    return UNITS.get(self.units, "kph")

  @property
  def speed_limit(self) -> int | None:
    """Limit in ``unit``; None when unknown, SNA or unlimited."""
    return SPEED_LIMIT.get(self.speed_code)

  @property
  def speed_limit_mps(self) -> float | None:
    value = self.speed_limit
    if value is None:
      return None
    return value * (MPH_TO_MPS if self.unit == "mph" else KPH_TO_MPS)

  @property
  def unlimited(self) -> bool:
    return self.speed_code == LIMIT_UNLIMITED

  @property
  def limit_known(self) -> bool:
    return self.speed_limit is not None

  @property
  def regular(self) -> bool:
    """REGULAR is the only type comparable with the car's fused limit; ADVISORY/DEPENDENT/BUMPS are not a hard limit."""
    return self.speed_type == 1

  @property
  def limit_type(self) -> str:
    return SPEED_TYPE.get(self.speed_type, "SNA")

  @property
  def dependency_label(self) -> str:
    return DEPENDENCY.get(self.dependency, "SNA")

  @property
  def road_label(self) -> str:
    return ROAD_CLASS.get(self.road_class, "SNA")

  @property
  def branch_distance_m(self) -> int | None:
    """Distance to the next branch in metres, or None when the frame says SNA."""
    if self.branch_raw >= BRANCH_SNA:
      return None
    return self.branch_raw * BRANCH_STEP_M

  @property
  def branch_side(self) -> str:
    if self.branch_left_ramp:
      return "L"
    if self.branch_right_ramp:
      return "R"
    return ""

  @property
  def reject_labels(self) -> tuple[str, ...]:
    """Short labels for the rejects that matter to a lane change: left/right lane, free space, autosteer, hands-on."""
    labels = []
    if self.reject_left:
      labels.append("L")
    if self.reject_right:
      labels.append("R")
    if self.reject_left_free:
      labels.append("LF")
    if self.reject_right_free:
      labels.append("RF")
    if self.reject_autosteer:
      labels.append("AS")
    if self.reject_hands_on:
      labels.append("HO")
    return tuple(labels)


def decode_frame(data: bytes) -> MapData | None:
  """Decode one 8-byte 0x238 payload, or None for a wrong length / non-bytes input."""
  if not isinstance(data, (bytes, bytearray)) or len(data) != 8:
    return None
  value = int.from_bytes(bytes(data), "little")
  return MapData(
    dependency=_bits(value, 0, 3),
    road_class=_bits(value, 3, 3),
    supercharger=bool(_bits(value, 6, 1)),
    units=_bits(value, 7, 1),
    speed_code=_bits(value, 8, 5),
    speed_type=_bits(value, 13, 3),
    country_code=_bits(value, 16, 10),
    street_count=_bits(value, 26, 2),
    gps_match=bool(_bits(value, 28, 1)),
    nav_active=bool(_bits(value, 29, 1)),
    parallel_autopark=bool(_bits(value, 30, 1)),
    perpendicular_autopark=bool(_bits(value, 31, 1)),
    branch_raw=_bits(value, 32, 5),
    controlled_access=bool(_bits(value, 37, 1)),
    branch_left_ramp=bool(_bits(value, 38, 1)),
    branch_right_ramp=bool(_bits(value, 39, 1)),
    reject_left=bool(_bits(value, 40, 1)),
    reject_right=bool(_bits(value, 41, 1)),
    reject_hpp=bool(_bits(value, 42, 1)),
    reject_nav=bool(_bits(value, 43, 1)),
    reject_left_free=bool(_bits(value, 44, 1)),
    reject_right_free=bool(_bits(value, 45, 1)),
    reject_autosteer=bool(_bits(value, 46, 1)),
    reject_hands_on=bool(_bits(value, 47, 1)),
    accept_botts=bool(_bits(value, 48, 1)),
    autosteer_restricted=bool(_bits(value, 49, 1)),
    pmm=bool(_bits(value, 50, 1)),
    sca=bool(_bits(value, 51, 1)),
  )


def is_fresh(received_ns: int, now_ns: int) -> bool:
  """True while the last frame is not in the future and not older than STALE_NS."""
  return 0 <= now_ns - received_ns <= STALE_NS
