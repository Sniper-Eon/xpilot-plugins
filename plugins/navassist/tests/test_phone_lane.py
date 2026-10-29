"""Failure contract: navigation recommendations or repeated/stale phone frames
must never masquerade as observed absolute ego position; stream/route reset and
native failure clear estimates without adding an unknown-lane veto."""
from navassist.phone_lane import PhoneLaneEvidence


def sample(stamp,frame,stream='camera-1'):
  return dict(version=1,source='tesnav-phone',valid=True,control_eligible=False,
    updated_mono_ns=stamp,frame_id=frame,stream_id=stream,
    lane_cp=dict(version=1,model='vlaneDay.mnn',leftClass=2,rightClass=2,
      laneNumber=2,laneCount=3,scope='visibleCorridor',control_eligible=False))


def test_distinct_frames_route_and_missing_data():
  gate=PhoneLaneEvidence();nav=dict(valid=True,sessionId='nav',routeRevision=1)
  for t in range(1,4):
    record=sample(t*100_000_000,t)
    r=gate.update(record,nav,t*100_000_000,enabled=True)
  assert r['valid'] and r['laneNumber']==2 and not r['absoluteConfirmed']
  assert not gate.update(record,dict(nav,routeRevision=2),300_000_000,enabled=True)['valid']
  assert not gate.update(record,nav,2_000_000_000,enabled=True)['valid']
  assert not gate.update(record,nav,300_000_000,enabled=False)['valid']
  assert not gate.update(None,nav,300_000_000,enabled=True)['valid']


def test_repeated_frames_bad_numbers_and_no_geometric_promotion():
  gate=PhoneLaneEvidence();nav=dict(valid=True,sessionId='nav',routeRevision=1)
  for _ in range(5):r=gate.update(sample(100,1),nav,100,enabled=True)
  assert r['valid'] and r['samples']==1
  record=sample(200,2);record['lane_cp']['laneNumber']=1
  assert not gate.update(record,nav,200,enabled=True)['valid']
  record=sample(300,3);record['lane_cp']['leftClass']=True
  assert not gate.update(record,nav,300,enabled=True)['valid']


def test_relabelled_old_frame_cannot_refresh_a_stable_estimate():
  gate=PhoneLaneEvidence();nav=dict(valid=True,sessionId='nav',routeRevision=1)
  for frame in (1,2,3):
    result=gate.update(sample(frame*100,frame),nav,frame*100,enabled=True)
  assert result['valid']
  assert not gate.update(sample(400,3),nav,400,enabled=True)['valid']


def test_transport_to_nav_hud_preserves_capture_and_never_sets_absolute_position(tmp_path):
  import json
  from phone_vision.frames import FrameStore
  from navassist.hud import present_hud
  now=[1_000_000_000];store=FrameStore(tmp_path/'observation.json',lambda:now[0])
  gate=PhoneLaneEvidence();nav=dict(valid=True,sessionId='nav',routeRevision=1)
  for i in range(1,4):
    now[0]+=100_000_000
    store.publish(dict(capture_mono_ns=now[0],frame_id=i,jpeg_b64='fixture'))
    packet=store.issue()
    body=dict(request_id=packet['request_id'],frame_id=i,left=None,right=None,lane_cp=sample(now[0],i)['lane_cp'])
    store.accept(body)
    result=gate.update(json.loads(store.output.read_text()),nav,now[0],enabled=True)
  assert result['valid'] and result['captureMonoNs']==now[0]
  hud=present_hud(dict(nav,phoneLaneEvidence=result),{},dict(valid=True,absoluteEgoIndex=None))
  assert hud['phone_lane_message']=='Vision lane estimate 2/3' and hud['ego'] is None
  store.new_stream()
  assert not gate.update(json.loads(store.output.read_text()),nav,now[0],enabled=True)['valid']


def test_single_frame_has_no_boundary_or_three_frame_wait():
  gate=PhoneLaneEvidence();nav=dict(valid=True,sessionId='nav',routeRevision=1)
  result=gate.update(sample(100,1),nav,100,enabled=True)
  assert result['valid'] and result['samples']==1
  assert result['laneNumber']==2 and not result['absoluteConfirmed']
