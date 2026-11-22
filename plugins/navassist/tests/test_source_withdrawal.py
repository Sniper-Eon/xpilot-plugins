"""Source withdrawal cannot be bypassed by the 1.5 s hold or turn-only path."""
from dataclasses import replace
import json
import pytest
from navassist import navstate
from navassist.store import NavAssistStore


def accepted():
  wall = 1_700_000_000_000
  body = dict(schemaVersion=3,messageType='navigation_snapshot',sessionId='phone-one',
              sequence=1,routeRevision=1,maneuverEventId=7,sourcePlatform='android',
              sourceWallTimeMs=wall,validForMs=1200,navigationMode='realtime',
              routeActive=True,routeMatched=True,gpsWeak=False,coordinateSystem='gcj02',
              location=dict(latitude=23.1,longitude=113.1,accuracyM=5,bearingDeg=90,speedKph=30,
                            observedAtMs=wall,currentStepIndex=0),
              guidance=dict(observedAtMs=wall,maneuver='turn_right',maneuverDistanceM=45))
  store = NavAssistStore(clock_ns=lambda:1_000_000_000,wall_clock_ms=lambda:wall)
  return store.accept(json.dumps(body).encode(),'a'*32)


@pytest.fixture(autouse=True)
def clean_hold(monkeypatch):
  monkeypatch.setattr(navstate,'_valid_hold',0)
  monkeypatch.setattr(navstate,'_valid_hold_key',None,raising=False)


@pytest.mark.parametrize('change',[
  dict(route_active=False),dict(navigation_mode='idle'),dict(navigation_mode='simulation'),
  dict(route_matched=False),dict(source_platform='track')])
def test_explicit_withdrawal_cancels_hold_and_turn_link(change):
  first = accepted()
  assert navstate.build(first,1_000_000_000)['valid']
  stopped = replace(first,snapshot=replace(first.snapshot,**change))
  output = navstate.build(stopped,1_100_000_000)
  assert not output['valid']
  assert not output['linked']


def test_transient_invalidity_can_hold_only_the_same_live_event():
  first = accepted()
  assert navstate.build(first,1_000_000_000)['valid']
  weak = replace(first,snapshot=replace(first.snapshot,gps_weak=True))
  assert navstate.build(weak,1_100_000_000)['valid']
  assert not navstate.build(weak,2_600_000_000)['valid']


@pytest.mark.parametrize('change',[
  dict(session_id='phone-two'),dict(route_revision=2),dict(maneuver_event_id=8)])
def test_new_source_route_or_event_cannot_inherit_old_validity(change):
  first = accepted()
  assert navstate.build(first,1_000_000_000)['valid']
  next_event = replace(first,snapshot=replace(first.snapshot,gps_weak=True,**change))
  assert not navstate.build(next_event,1_100_000_000)['valid']
