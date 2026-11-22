"""Failure cases recorded before the fix:
an old count survives indefinitely; another road/route inherits it; an interrupted
candidate counts as continuous; heartbeats renew old evidence; disabled features
retain the count. None of these cases may invent a lane number or a lane change.
"""
from dataclasses import replace
import json
from types import SimpleNamespace as N

import pytest
from navassist.runtime import NavigationRuntime
from navassist.settings import NavSettings
from navassist.store import NavAssistStore


def tick(runtime, seconds, count=4, *, road='Road A', revision=1, observed=None,
         maneuver='straight'):
  ns = int(seconds * 1e9)
  wall = 1_700_000_000_000 + int(seconds * 1000)
  body = dict(schemaVersion=3, messageType='navigation_snapshot', sessionId='phone',
              sequence=int(seconds * 1000), routeRevision=revision, maneuverEventId=7,
              sourcePlatform='android', sourceWallTimeMs=wall, validForMs=1200,
              navigationMode='realtime', routeActive=True, routeMatched=True,
              gpsWeak=False, coordinateSystem='gcj02',
              location=dict(latitude=23.1, longitude=113.1, accuracyM=4,
                            bearingDeg=90, speedKph=36, observedAtMs=wall, currentStepIndex=0),
              guidance=dict(observedAtMs=wall, maneuver=maneuver, maneuverDistanceM=2000,
                            currentRoad=road))
  if count:
    body['lanes'] = dict(observedAtMs=wall if observed is None else observed, totalCount=count,
                         items=[dict(index=i, recommended=True, allowedActions=['STRAIGHT'],
                                     recommendedActions=['STRAIGHT'])
                                for i in range(count)])
  store = NavAssistStore(clock_ns=lambda:ns, wall_clock_ms=lambda:wall)
  current = store.accept(json.dumps(body).encode(), 'a' * 32)
  return runtime.tick(current, None, 0, N(vEgo=10.), N(latActive=False), ns,
                      vehicle_fresh=True)


def confirmed():
  runtime = NavigationRuntime(NavSettings())
  tick(runtime, 1)
  tick(runtime, 2.1)
  assert runtime._road_total == 4
  return runtime


def test_absent_lane_callbacks_eventually_expire_confirmed_count():
  runtime = confirmed()
  output = tick(runtime, 100, count=0)
  assert runtime._road_total is None
  assert not output['intent'].get('spLaneChangeReady')
  if output['topology'].get('fnav'):
    assert not output['topology']['fnav'].get('n')


@pytest.mark.parametrize('change', [dict(road='Road B'), dict(revision=2)])
def test_new_road_or_route_cannot_inherit_old_count(change):
  runtime = confirmed()
  tick(runtime, 3, count=0, **change)
  assert runtime._road_total is None


def test_gap_restarts_candidate_confirmation():
  runtime = NavigationRuntime(NavSettings())
  tick(runtime, 1)
  tick(runtime, 2, count=0)
  tick(runtime, 3)
  assert runtime._road_total is None
  tick(runtime, 4.1)
  assert runtime._road_total == 4


def test_disabled_feature_clears_count():
  runtime = confirmed()
  runtime.settings = replace(runtime.settings, enabled=False)
  tick(runtime, 3, count=0)
  assert runtime._road_total is None


def test_old_lane_timestamp_in_new_heartbeats_does_not_renew_count():
  runtime = confirmed()
  original = 1_700_000_002_100
  for seconds in (3, 7, 15, 50, 100):
    tick(runtime, seconds, observed=original)
  assert runtime._road_total is None


def test_expiry_does_not_promote_future_junction_layout():
  runtime = confirmed()
  for seconds in (100,101,103):
    output=tick(runtime,seconds,count=5,maneuver='slight_right')
  assert runtime._road_total is None
  if output['topology'].get('laneV3'):
    assert output['topology']['laneV3'].get('road_layout_unknown')


def test_new_road_cannot_reconfirm_an_old_road_callback():
  runtime=confirmed()
  for seconds in (3,4.1):
    tick(runtime,seconds,road='Road B',observed=1_700_000_002_100)
  assert runtime._road_total is None
