"""Map limit vs fused limit: one step is not a conflict, two steps held 3 s is, untrusted map data never is."""
import pytest

from ..compare import (AGREE, CONFLICT_CONFIRM_NS, MAP_HIGHER, MAP_LOWER, MAP_ONLY, NONE, SP_ONLY,
                       LimitComparator, to_units)

KPH = 1 / 3.6


def test_to_units():
  assert to_units(60 * KPH, "kph") == 60
  assert to_units(60 * 0.44704, "mph") == 60
  assert to_units(0.0, "kph") is None
  assert to_units(-1.0, "kph") is None


def test_one_step_of_difference_agrees():
  c = LimitComparator()
  low = c.update(60, "kph", 65 * KPH, 1_000)
  high = c.update(65, "kph", 60 * KPH, 1_000)
  assert low.state == AGREE and low.delta == -5 and not low.conflict
  assert high.state == AGREE and high.delta == 5 and not high.conflict


def test_two_steps_classify_and_conflict_after_the_hold():
  c = LimitComparator()
  first = c.update(60, "kph", 75 * KPH, 1_000, trusted=True)
  assert (first.state, first.delta) == (MAP_LOWER, -15)
  assert not first.conflict, "the hold must start, not fire on the first sample"
  held = c.update(60, "kph", 75 * KPH, 1_000 + CONFLICT_CONFIRM_NS, trusted=True)
  assert held.conflict
  higher = LimitComparator().update(100, "kph", 60 * KPH, 1_000)
  assert (higher.state, higher.delta) == (MAP_HIGHER, 40)


def test_conflict_clears_and_rearms():
  c = LimitComparator()
  c.update(60, "kph", 75 * KPH, 0)
  assert c.update(60, "kph", 75 * KPH, 0 + CONFLICT_CONFIRM_NS).conflict
  agreed = c.update(60, "kph", 60 * KPH, 0 + CONFLICT_CONFIRM_NS + 1)
  assert agreed.state == AGREE and not agreed.conflict
  again = c.update(60, "kph", 75 * KPH, 0 + CONFLICT_CONFIRM_NS + 2)
  assert not again.conflict
  assert c.update(60, "kph", 75 * KPH, 0 + 2 * CONFLICT_CONFIRM_NS + 2).conflict


def test_untrusted_map_data_never_conflicts():
  c = LimitComparator()
  for now in (0, CONFLICT_CONFIRM_NS, 2 * CONFLICT_CONFIRM_NS):
    assert not c.update(60, "kph", 75 * KPH, now, trusted=False).conflict


def test_missing_side_classification():
  c = LimitComparator()
  assert c.update(None, "kph", 60 * KPH, 0).state == SP_ONLY
  assert c.update(60, "kph", 0.0, 0).state == MAP_ONLY
  both = c.update(None, "kph", 0.0, 0)
  assert both.state == NONE and both.map_value is None and both.sp_value is None


def test_mph_units_compare_in_mph():
  c = LimitComparator()
  result = c.update(65, "mph", 65 * 0.44704, 0)
  assert (result.state, result.sp_value, result.delta) == (AGREE, 65, 0)


@pytest.mark.parametrize("map_limit,sp_mps,state", [
  (None, 0.0, NONE),
  (60, 0.0, MAP_ONLY),
  (None, 10.0, SP_ONLY),
])
def test_states_without_both_values(map_limit, sp_mps, state):
  assert LimitComparator().update(map_limit, "kph", sp_mps, 0).state == state
