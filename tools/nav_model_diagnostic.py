"""Real pinned ONNX diagnostic; synthetic black camera, NOT a road replay.

Failure contract before running: wrong weights, nonfinite outputs, missing state,
incorrect state ABI, state aliasing, nondeterminism on identical history, and
mistaking zeroed current input for erased history must be exposed. No vehicle IPC.
"""
import argparse
import base64
import hashlib
import io
import json
import pickle
from pathlib import Path
import time
import numpy as np
from PIL import Image
from tools.nav_model_sequence import verify_weights, MODEL_SHA256
from tools.nav_model_trial import navigation_input


class SliceOnly(pickle.Unpickler):
  def find_class(self,module,name):
    if (module,name)==('builtins','slice'):return slice
    raise ValueError('unsupported model metadata object')


def diagnose(model, image, output):
  verify_weights(model)
  if output.exists():raise ValueError('output directory already exists')
  import onnxruntime as ort
  opts=ort.SessionOptions();opts.intra_op_num_threads=4;opts.inter_op_num_threads=1;opts.log_severity_level=3
  session=ort.InferenceSession(str(model),opts,providers=['CPUExecutionProvider'])
  slices=SliceOnly(io.BytesIO(base64.b64decode(session.get_modelmeta().custom_metadata_map['output_slices']))).load()
  with Image.open(image) as im:
    if im.mode!='L' or im.size!=(256,256):raise ValueError('map must be L/256x256')
    pixels=np.array(im,dtype=np.float32).reshape(1,1,256,256)
  names=[x.name for x in session.get_outputs()]
  feed={x.name:np.zeros(x.shape,np.uint8 if x.type=='tensor(uint8)' else np.float32) for x in session.get_inputs()}
  if feed['new_img'].shape!=(2,6,128,256):raise ValueError('camera ABI differs')
  feed['traffic_convention'][0,0]=1;feed['action_t'][:]=.5
  states={k:v for k,v in feed.items() if k.startswith('state_')}
  fixed={k:v for k,v in feed.items() if k not in states}
  zero_map=fixed['nav_map'];zero_nav=fixed['navigation'];times=[]
  state_names=tuple(states)

  def copy(state):return {k:v.copy() for k,v in state.items()}

  def step(state,mp,nav):
    start=time.perf_counter()
    values=session.run(None,dict(fixed,**state,nav_map=mp,navigation=nav))
    times.append(time.perf_counter()-start)
    if len(values)!=len(names) or not all(np.isfinite(v).all() for v in values):
      raise ValueError('invalid model outputs')
    out=dict(zip(names,values));nxt={}
    for k in state_names:
      a=out['next_'+k]
      if a.shape!=state[k].shape or a.dtype!=state[k].dtype:raise ValueError('state ABI mismatch')
      nxt[k]=a.copy()
    return out['outputs'].copy(),nxt

  for i in range(140):
    _,states=step(states,zero_map,zero_nav)
    if (i+1)%20==0:print('warmup',i+1,flush=True)
  snapshot=copy(states);snapshot_hash={k:hashlib.sha256(v.tobytes()).hexdigest() for k,v in snapshot.items()}
  left=navigation_input([dict(type='turn',modifier='left',distance=100)],0)
  right=navigation_input([dict(type='turn',modifier='right',distance=100)],0)
  branches={}
  for name,mp,nav in [('blank',zero_map,zero_nav),('map_only',pixels,zero_nav),
                      ('left',pixels,left),('right',pixels,right),('nav_only',zero_map,right),
                      ('blank_repeat',zero_map,zero_nav)]:
    raw,_=step(copy(snapshot),mp,nav);branches[name]=raw
  if not np.array_equal(branches['blank'],branches['blank_repeat']):raise ValueError('nonrepeatable identical history')
  assert snapshot_hash=={k:hashlib.sha256(v.tobytes()).hexdigest() for k,v in snapshot.items()}
  temporal=[];baseline=[];a,b=copy(snapshot),copy(snapshot)
  for i in range(164):
    on=i<24
    raw,a=step(a,pixels if on else zero_map,right if on else zero_nav)
    base,b=step(b,zero_map,zero_nav)
    temporal.append(raw);baseline.append(base)
    if (i+1)%20==0:print('paired navigation/on-off',i+1,flush=True)
  temporal=np.stack(temporal);baseline=np.stack(baseline)
  def diff(a,b,key):return float(np.max(np.abs(a[...,slices[key]]-b[...,slices[key]])))
  report=dict(officialInferenceExecuted=True,modelSha256=MODEL_SHA256,frames=len(times),
    backend='ONNX Runtime CPU',syntheticBlackCamera=True,historicalUnpairedMap=True,
    warmupFrames=140,navigationOnFrames=24,navigationWithdrawnFrames=140,
    matchedRoadReplay=False,cameraWarpValidated=False,gpuValidated=False,deviceActivated=False,
    sameHistoryRepeatExact=True,snapshotUnchanged=True,
    secondsMedian=float(np.median(times)),secondsP95=float(np.percentile(times,95)),
    branches={k:dict(actionMaxAbsDiff=diff(v,branches['blank'],'action'),
                    planMaxAbsDiff=diff(v,branches['blank'],'plan')) for k,v in branches.items()},
    withdrawal={str(i):dict(actionMaxAbsDiff=diff(temporal[24+i-1],baseline[24+i-1],'action'),
                            planMaxAbsDiff=diff(temporal[24+i-1],baseline[24+i-1],'plan'))
                for i in [1,20,60,128,140]},
    limitations=['synthetic camera tensors; no road quality or maneuver safety conclusion',
                 'action_t fixed to diagnostic .5s; inputs represent no moving vehicle',
                 '140 warmup updates do not prove recurrent state convergence'])
  output.mkdir(parents=True)
  np.savez_compressed(output/'outputs.npz',temporal=temporal,baseline=baseline,**branches)
  (output/'result.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
  print(json.dumps(report),flush=True)


def main():
  p=argparse.ArgumentParser(description=__doc__)
  p.add_argument('model',type=Path);p.add_argument('map',type=Path);p.add_argument('output',type=Path)
  a=p.parse_args();diagnose(a.model,a.map,a.output)


if __name__=='__main__':main()
