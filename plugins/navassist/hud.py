"""Presentation only: preserve absence/staleness and never infer a current lane."""
import math
from .display import guidance_visible


def hud_rect(bottom):
  x,y,w,h=bottom
  return x+16,y+16,max(0,w-32),max(0,h-32)


def present_hud(nav,intent,topology,*,car=None,authority=None):
  active=guidance_visible(nav)
  stale=bool(nav.get('routeActive') and nav.get('stale',True))
  distance=nav.get('distanceM')
  distance=distance if active and type(distance) in (int,float) and math.isfinite(distance) and distance>=0 else None
  count=nav.get('laneTotalCount',0)
  count=count if type(count) is int and 1<=count<=16 and active else 0
  recommended=tuple(sorted({r['index'] for r in nav.get('lanes',[]) if isinstance(r,dict)
    and r.get('recommended') and type(r.get('index')) is int and 0<=r['index']<count})) if count else ()
  ego=topology.get('absoluteEgoIndex')
  ego=ego if nav.get('valid') and topology.get('valid') and type(ego) is int and 0<=ego<count else None
  status='Navigation linked' if active else 'Navigation data delayed' if stale else 'Waiting for phone navigation'
  tone='cyan' if active and nav.get('valid') else 'amber' if active or stale else 'dim'
  if active and not nav.get('valid'):status='Guidance only'
  if intent.get('valid') and intent.get('signalRequested'):
    side=intent.get('direction')
    same=bool(car and side in ('left','right') and car.get(side+'Blinker') and not car.get(('right' if side=='left' else 'left')+'Blinker'))
    if same:status,tone='Vehicle signal confirmed','cyan'
    elif authority is False:status,tone='Auto signal permission unavailable','amber'
    else:status,tone='Waiting for vehicle signal','amber'
  return dict(active=active,distance=distance,maneuver=nav.get('maneuver') if active else None,
    status=status,tone=tone,count=count,recommended=recommended,ego=ego,
    lane_status='Lane position confirmed' if ego is not None else 'Lane position pending')
