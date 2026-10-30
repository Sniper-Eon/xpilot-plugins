"""Join recorded per-frame navigation/map envelopes with prepared camera tensors.

Offline only. Producer must supply timestamps already converted to one monotonic
clock; this tool cannot prove capture synchronization or coordinate correctness.
"""
import argparse
import json
from pathlib import Path
import numpy as np
from PIL import Image
from tools.nav_model_trial import build_inputs

BASE={'new_img':(2,6,128,256),'desire':(8,), 'traffic_convention':(1,2),'action_t':(1,2)}


def prepare_feeds(camera, records, load_map):
  if set(camera)!=set(BASE):raise ValueError('prepared camera/base feed names mismatch')
  if not records:raise ValueError('no records')
  for k,shape in BASE.items():
    a=camera[k];dtype=np.uint8 if k=='new_img' else np.float32
    if a.shape!=(len(records),*shape) or a.dtype!=dtype or not np.isfinite(a).all():
      raise ValueError('prepared camera/base feed ABI mismatch: '+k)
  maps=np.zeros((len(records),1,1,256,256),np.float32)
  navigation=np.zeros((len(records),1,47),np.float32);reasons=[]
  for i,r in enumerate(records):
    if not isinstance(r,dict):raise ValueError('invalid record')
    # Missing map never reuses a prior frame. No filesystem work in modeld.
    pixels=load_map(r) if r.get('enabled') is True else None
    inputs,reason=build_inputs(r.get('nav'),r.get('frame'),pixels,
                              now=r.get('now'),speed=r.get('speed'),enabled=r.get('enabled'))
    if inputs:maps[i],navigation[i]=inputs['nav_map'],inputs['navigation']
    reasons.append(reason)
  return dict(camera,nav_map=maps,navigation=navigation),reasons


def main():
  p=argparse.ArgumentParser(description=__doc__)
  p.add_argument('camera',type=Path);p.add_argument('records',type=Path,help='JSONL; map is relative to this file')
  p.add_argument('output',type=Path,help='New directory')
  args=p.parse_args()
  records=[json.loads(l) for l in args.records.read_text().splitlines() if l.strip()]
  def load_map(r):
    path=r.get('map')
    if not isinstance(path,str):return None
    try:
      with Image.open(args.records.parent/path) as im:
        return np.array(im) if im.mode=='L' and im.size==(256,256) else None
    except (OSError,ValueError):return None
  with np.load(args.camera,allow_pickle=False) as z:
    feeds,reasons=prepare_feeds({k:z[k] for k in z.files},records,load_map)
  args.output.mkdir(parents=True,exist_ok=False)
  np.savez_compressed(args.output/'feeds.npz',**feeds)
  report=dict(frames=len(records),reasons=reasons,matchedCaptureProven=False,
              sdkConnected=False,phoneConnected=False,deviceActivated=False)
  (args.output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
  print(json.dumps(report))


if __name__=='__main__':main()
