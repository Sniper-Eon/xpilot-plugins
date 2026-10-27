"""Failures: stale data looks live; unknown lanes masquerade as lane zero;
missing turn-signal authority/feedback is shown as ready; HUD covers road alerts.
"""
from navassist.hud import present_hud, hud_rect


def test_missing_stale_and_unqualified_data_are_distinct():
  assert present_hud({}, {}, {})['status']=='Waiting for phone navigation'
  state=present_hud(dict(routeActive=True,stale=True,maneuver='turn_right',distanceM=30),{}, {})
  assert state['status']=='Navigation data delayed' and state['distance'] is None
  state=present_hud(dict(valid=True,linked=True,stale=False,maneuver='turn_right',distanceM=30,laneTotalCount=3),{}, {})
  assert state['ego'] is None and state['lane_status']=='Lane position pending'


def test_requested_lamp_is_not_reported_as_executed():
  nav=dict(valid=True,linked=True,stale=False,maneuver='turn_right',distanceM=30)
  intent=dict(valid=True,signalRequested=True,direction='right',targetLaneIndex=-1,signalPurpose='junction')
  state=present_hud(nav,intent,{},car=dict(leftBlinker=False,rightBlinker=False),authority=False)
  assert state['status']=='Auto signal permission unavailable' and state['tone']=='amber'
  state=present_hud(nav,intent,{},car=dict(leftBlinker=False,rightBlinker=True),authority=False)
  assert state['status']=='Vehicle signal confirmed'


def test_recommendations_never_become_an_observed_ego_lane():
  nav=dict(valid=True,linked=True,stale=False,maneuver='turn_left',distanceM=80,laneTotalCount=3,
           lanes=[dict(index=0,recommended=True)])
  state=present_hud(nav,{},dict(valid=True,absoluteEgoIndex=None))
  assert state['recommended']==(0,) and state['ego'] is None
  assert present_hud(nav,{},dict(valid=True,absoluteEgoIndex=1))['ego']==1


def test_hud_stays_inside_bottom_strip_and_off_the_road_view():
  x,y,w,h=hud_rect((300,764,1560,316))
  assert x>=300 and y>=764 and x+w<=1860 and y+h<=1080
  assert w>1000 and h>180


def test_link_alone_does_not_show_an_inactive_or_replay_route_as_live():
  for nav in (dict(linked=True,stale=False,routeActive=False,maneuver='turn_right',mode='realtime'),
              dict(linked=True,stale=False,routeActive=True,maneuver='turn_right',mode='preview'),
              dict(linked=True,stale=False,routeActive=True,maneuver='none',mode='realtime')):
    state=present_hud(nav,{}, {})
    assert not state['active'] and state['maneuver'] is None
