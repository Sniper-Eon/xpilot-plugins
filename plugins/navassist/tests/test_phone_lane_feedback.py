"""The HUD model observation must reach phone feedback, with its original age;
legacy absolute-lane feedback and legacy ACK shapes must remain unchanged."""
import json
from types import SimpleNamespace as N
from navassist.feedback import lane_model_feedback


def test_single_frame_estimate_feedback_is_route_bound_and_expires(tmp_path):
  path=tmp_path/'estimate.json';now=1_000_000_000
  data=dict(version=1,valid=True,laneNumber=2,laneCount=3,captureMonoNs=now,
    source='cpPhoneVision',scope='visibleCorridor',controlEligible=False,
    navSessionId='s',routeRevision=2)
  path.write_text(json.dumps(data));snap=N(session_id='s',route_revision=2)
  out=lane_model_feedback(snap,path=path,now_ns=now)
  assert out['valid'] and out['laneNumber']==2 and out['laneCount']==3
  assert not lane_model_feedback(snap,path=path,now_ns=now+800_000_001)['valid']
  assert not lane_model_feedback(N(session_id='new',route_revision=2),path=path,now_ns=now)['valid']
  assert not lane_model_feedback(N(session_id='s',route_revision=3),path=path,now_ns=now)['valid']
