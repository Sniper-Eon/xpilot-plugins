"""Before alignment: local runtime still selects the geometric matcher; current
fusion/V3 modules are absent; feedback mixes wall and monotonic clocks. Retain
the source-withdrawal and current-road memory repairs while importing device code.
"""
import json
import os
from types import SimpleNamespace as N


def test_runtime_selects_the_actual_device_fused_pipeline():
  from navassist.runtime import NavigationRuntime
  from navassist.settings import NavSettings
  runtime=NavigationRuntime(NavSettings())
  assert type(runtime._geo_lane).__name__=='FusedLaneMatcher'
  assert hasattr(runtime,'_lane_v3')
  assert runtime._geo_lane.pipe.gps_jump is None
  assert runtime._geo_lane.pipe.use_dr and runtime._geo_lane.pipe.use_vision


def test_phone_feedback_uses_one_clock_for_expiry_and_age(tmp_path,monkeypatch):
  from navassist import feedback
  wall=1_800_000_000_000_000_000
  path=tmp_path/'phone.json'
  path.write_text(json.dumps(dict(version=1,valid=True,laneNumber=2,laneCount=3,
    source='cpPhoneVision',scope='visibleCorridor',controlEligible=False,
    navSessionId='s',routeRevision=2)))
  os.utime(path,ns=(wall,wall))
  monkeypatch.setattr(feedback.time,'time_ns',lambda:wall+120_000_000)
  out=feedback.lane_model_feedback(N(session_id='s',route_revision=2),path=path,now_ns=9_000_000_000)
  assert out['valid'] and out['ageMs']==120
  monkeypatch.setattr(feedback.time,'time_ns',lambda:wall+800_000_001)
  assert not feedback.lane_model_feedback(N(session_id='s',route_revision=2),path=path,now_ns=9_000_000_001)['valid']


def test_recommendation_thresholds_remain_the_current_contract():
  from navassist.rec_gate import rec_gate_m
  assert rec_gate_m('regular','straight')==250
  assert rec_gate_m('expressway','straight')==800
  assert rec_gate_m('urban_expressway','straight')==640
  assert rec_gate_m('regular','turn_right')==400
