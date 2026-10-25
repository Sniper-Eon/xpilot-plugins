"""Chime contract: only a fresh navigation-owned SP start, once per request.
Manual changes, preparation, expired input and disabled settings stay silent.
"""
from types import SimpleNamespace as N
from .test_migration_contract import Params, Messages


def test_navigation_start_chime_is_single_and_never_manual():
  from navassist.chime import NavigationChime
  source = NavigationChime(Params())
  source.settings = N(enabled=True, beep_enabled=True)
  source._msgs = Messages({})
  sm = {'modelV2': N(meta=N(laneChangeState='laneChangeStarting', laneChangeDirection='left'))}
  assert source.update(sm) == []
  intent = dict(valid=True, signalRequested=True, direction='left', targetLaneIndex=0,
                spLaneChangeReady=True, laneChangeAllowed=True, requestId=4,
                sessionId='s', routeRevision=1, maneuverEventId=9)
  source._msgs = Messages({'lanes.intent': {'navassist': intent}})
  sm['modelV2'].meta.laneChangeState = 'preLaneChange'
  assert source.update(sm) == []
  sm['modelV2'].meta.laneChangeState = 'laneChangeStarting'
  assert len(source.update(sm)) == 1
  assert source.update(sm) == []
  source.settings.beep_enabled = False
  intent['requestId'] = 5
  assert source.update(sm) == []
  source.settings.beep_enabled = True
  intent['targetLaneIndex'] = -1
  assert source.update(sm) == []
