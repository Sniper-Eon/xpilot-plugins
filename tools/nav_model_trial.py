"""Offline navigation-model input experiment; never imported by a vehicle process.

Official encoding reference: commaai/openpilot afbf2e547e9319e2eb9f515e1e4330af63705cec,
openpilot/selfdrive/navigation/helpers.py. This is NOT a complete model feed or
permission to actuate. Map images must already follow the training geometry/style.
"""
import argparse
import json
import math
from pathlib import Path
import numpy as np

REFERENCE = 'afbf2e547e9319e2eb9f515e1e4330af63705cec'
SIDED = {'depart': (1,2,3), 'arrive': (4,5,6), 'on ramp': (17,18,19),
         'off ramp': (20,20,21), 'fork': (22,23,24), 'roundabout': (26,26,26),
         'rotary': (26,26,26), 'roundabout turn': (26,26,26),
         'exit roundabout': (27,27,27), 'exit rotary': (27,27,27), 'notification': (28,28,28)}
TURNS = {'straight':8, 'slight right':9, 'right':10, 'sharp right':11, 'uturn':13,
         'sharp left':14, 'left':15, 'slight left':16}


def numeric(value):
  return type(value) in (int, float) and math.isfinite(value)


def navigation_input(maneuvers, traveled):
  """Same command selection as the pinned official helper; bounded input only."""
  result = np.zeros((1,47), dtype=np.float32)
  for m in maneuvers:
    kind, modifier = m['type'], m['modifier']
    if kind == 'merge':
      continue
    if kind in SIDED:
      straight, right, left = SIDED[kind]
      command = right if 'right' in modifier else left if 'left' in modifier else straight
    else:
      command = TURNS.get(modifier,8)
    distance = m['distance'] - traveled
    if command > 6 and distance >= 0:
      result[0,command], result[0,-1] = 1, distance/100
      break
  return result


def build_inputs(nav, frame, pixels, *, now, speed, enabled):
  """All-or-nothing diagnostic admission; no retained state or driving authority."""
  if enabled is not True:
    return {}, 'disabled'
  if not numeric(now) or not numeric(speed) or speed < 0 or speed > 100:
    return {}, 'invalid_clock_or_speed'
  if not isinstance(nav,dict) or not isinstance(frame,dict):
    return {}, 'missing_input'
  if nav.get('valid') is not True or frame.get('valid') is not True:
    return {}, 'invalid_input'
  if nav.get('positioningQualified') is not True or nav.get('mode') != 'realtime':
    return {}, 'unqualified_source'
  context = nav.get('context')
  if (not isinstance(context,dict) or set(context) != {'session','revision','route'} or
      any(not isinstance(context[k],str) or not context[k] for k in ('session','route')) or
      type(context['revision']) is not int or context['revision'] < 0 or context != frame.get('context')):
    return {}, 'route_mismatch'
  for source, ttl in ((nav,2.),(frame,.5)):
    stamp=source.get('mono')
    if not numeric(stamp) or not 0 <= now-stamp < ttl:
      return {}, 'expired_or_future'
  if not isinstance(pixels,np.ndarray) or pixels.shape != (256,256) or pixels.dtype != np.uint8:
    return {}, 'invalid_map'
  if not np.any(pixels):
    return {}, 'empty_map'
  maneuvers=nav.get('maneuvers')
  if not isinstance(maneuvers,list) or len(maneuvers)>256:
    return {}, 'invalid_maneuvers'
  for m in maneuvers:
    if (not isinstance(m,dict) or not numeric(m.get('distance')) or abs(m['distance'])>30_000_000 or
        any(not isinstance(m.get(k),str) or len(m[k])>64 for k in ('type','modifier'))):
      return {}, 'invalid_maneuvers'
  return {'nav_map':pixels.astype(np.float32).reshape(1,1,256,256),
          'navigation':navigation_input(maneuvers,speed*(now-nav['mono']))}, 'ready'


def main():
  parser=argparse.ArgumentParser(description=__doc__)
  parser.add_argument('request',type=Path,help='Offline JSON envelope with nav/frame/now/speed/enabled')
  parser.add_argument('map',type=Path,help='256x256 grayscale PNG; no implicit conversion or resizing')
  parser.add_argument('output',type=Path,help='New output directory (must not exist)')
  args=parser.parse_args()
  from PIL import Image
  request=json.loads(args.request.read_text())
  with Image.open(args.map) as im:
    if im.mode != 'L' or im.size != (256,256):
      raise ValueError('map must be grayscale L, 256x256')
    pixels=np.array(im)
  inputs,reason=build_inputs(request.get('nav'),request.get('frame'),pixels,now=request.get('now'),
                             speed=request.get('speed'),enabled=request.get('enabled'))
  args.output.mkdir(parents=True,exist_ok=False)
  if inputs:
    np.savez(args.output/'optional-inputs.npz',**inputs)
  report=dict(reference=REFERENCE,reason=reason,optionalInputsReady=bool(inputs),
              inferenceRun=False,deviceActivated=False,actuationPermitted=False,
              synchronizedCaptureProven=False)
  (args.output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
  print(json.dumps(report))
  return 0 if inputs else 2


if __name__ == '__main__':
  raise SystemExit(main())
