"""Arbitration between Tesla's map limit (0x238) and the limit sunnypilot already resolves.

Display-only here: the result feeds the tile and the published snapshot, never a control output. Rules:

- The map code is an upper bound in the car's display unit, so one step (5 units) of difference is not a conflict.
- Two steps (10 units) or more, held for CONFLICT_CONFIRM_NS, is a conflict. It is reported only when the map frame is
  REGULAR, GPS-matched and fresh, so a stale or advisory map value never raises one.
- A conflict clears as soon as the values agree again; the hold restarts from zero.
"""
from __future__ import annotations

from dataclasses import dataclass

AGREE_UNITS = 5
CONFLICT_UNITS = 10
CONFLICT_CONFIRM_NS = 3_000_000_000

AGREE = "AGREE"
MAP_HIGHER = "MAP_HIGHER"
MAP_LOWER = "MAP_LOWER"
MAP_ONLY = "MAP_ONLY"
SP_ONLY = "SP_ONLY"
NONE = "NONE"

KPH_PER_MPS = 3.6
MPH_PER_MPS = 1.0 / 0.44704


@dataclass(frozen=True)
class Comparison:
  state: str
  map_value: int | None
  sp_value: int | None
  delta: int | None
  conflict: bool

  @property
  def known(self) -> bool:
    return self.state != NONE


def to_units(speed_mps: float, unit: str) -> int | None:
  """A positive speed in m/s as the rounded integer the car shows, or None for 0/invalid."""
  if not speed_mps or speed_mps <= 0.0:
    return None
  return int(round(speed_mps * (MPH_PER_MPS if unit == "mph" else KPH_PER_MPS)))


class LimitComparator:
  """Stateful only for the conflict hold; everything else is a pure function of the two limits."""

  def __init__(self, agree_units: int = AGREE_UNITS, conflict_units: int = CONFLICT_UNITS,
               confirm_ns: int = CONFLICT_CONFIRM_NS):
    self.agree_units = agree_units
    self.conflict_units = conflict_units
    self.confirm_ns = confirm_ns
    self._conflict_since: int | None = None

  def _classify(self, map_value: int, sp_value: int) -> str:
    delta = map_value - sp_value
    if abs(delta) <= self.agree_units:
      return AGREE
    return MAP_HIGHER if delta > 0 else MAP_LOWER

  def update(self, map_limit: int | None, unit: str, sp_mps: float, now_ns: int,
             trusted: bool = True) -> Comparison:
    """map_limit: decoded code value in ``unit`` (None when unknown/unlimited); sp_mps: carStateSP.speedLimit."""
    sp_value = to_units(sp_mps, unit)
    if map_limit is None and sp_value is None:
      self._conflict_since = None
      return Comparison(NONE, None, None, None, False)
    if map_limit is None:
      self._conflict_since = None
      return Comparison(SP_ONLY, None, sp_value, None, False)
    if sp_value is None:
      self._conflict_since = None
      return Comparison(MAP_ONLY, map_limit, None, None, False)

    delta = map_limit - sp_value
    state = self._classify(map_limit, sp_value)
    if not trusted or abs(delta) < self.conflict_units:
      self._conflict_since = None
      return Comparison(state, map_limit, sp_value, delta, False)

    if self._conflict_since is None:
      self._conflict_since = now_ns
    conflict = now_ns - self._conflict_since >= self.confirm_ns
    return Comparison(state, map_limit, sp_value, delta, conflict)
