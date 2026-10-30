"""Offline recurrent ONNX replay. No vehicle IPC, compiled pickle or actuation.

Weights are pinned to the historical navigation ONNX, not the later compiled
artifact. Prepared camera feeds must come from separately verified preprocessing.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
import numpy as np

MODEL_SHA256='1d18c42ea4cd95c8bffab4635844b78b8e2d4e25b9de44a9c5ac2e0961371a2e'
MODEL_BYTES=814591106
DTYPES={'tensor(uint8)':np.dtype('uint8'),'tensor(float)':np.dtype('float32')}


def verify_weights(path):
  if path.stat().st_size != MODEL_BYTES:
    raise ValueError('navigation ONNX size mismatch')
  h=hashlib.sha256()
  with path.open('rb') as f:
    for block in iter(lambda:f.read(4*1024*1024),b''):h.update(block)
  if h.hexdigest()!=MODEL_SHA256:
    raise ValueError('navigation ONNX SHA256 mismatch')


def run_sequence(session, feeds):
  """Validate ALL frames before inference; advance every state from its next head.

  Returns raw model outputs, no driving-metric interpretation. Initial state is
  zero; callers must allow full warmup and must not mistake this for native GPU
  equivalence or synchronized route/camera evidence.
  """
  specs=session.get_inputs();names=[x.name for x in session.get_outputs()]
  states={};length=None
  expected={x.name for x in specs if not x.name.startswith('state_')}
  if set(feeds)!=expected:raise ValueError('prepared feed names differ from model ABI')
  for x in specs:
    if x.type not in DTYPES or any(type(n) is not int or n<=0 for n in x.shape):
      raise ValueError('unsupported model ABI')
    if x.name.startswith('state_'):
      if 'next_'+x.name not in names:raise ValueError('missing next-state head')
      states[x.name]=np.zeros(x.shape,DTYPES[x.type]);continue
    a=feeds[x.name]
    if a.dtype!=DTYPES[x.type] or a.ndim!=len(x.shape)+1 or tuple(a.shape[1:])!=tuple(x.shape):
      raise ValueError('prepared input shape/dtype mismatch: '+x.name)
    if not len(a) or not np.isfinite(a).all():raise ValueError('empty or nonfinite feed')
    if length is not None and length!=len(a):raise ValueError('frame counts differ')
    length=len(a)
  if length is None:raise ValueError('no frame feeds')
  rows=[]
  for i in range(length):
    feed={k:v[i] for k,v in feeds.items()};feed.update(states)
    start=time.perf_counter();values=session.run(None,feed);elapsed=time.perf_counter()-start
    if len(values)!=len(names):raise ValueError('output count mismatch')
    out=dict(zip(names,values))
    if any(not np.isfinite(v).all() for v in values):raise ValueError('nonfinite model output')
    if 'outputs' not in out:raise ValueError('missing primary output')
    for key,old in states.items():
      nxt=out['next_'+key]
      if nxt.shape!=old.shape or nxt.dtype!=old.dtype:raise ValueError('next-state ABI mismatch')
      states[key]=nxt.copy()
    rows.append(dict(outputs=out['outputs'].copy(),seconds=elapsed))
  return rows


def main():
  parser=argparse.ArgumentParser(description=__doc__)
  parser.add_argument('model',type=Path);parser.add_argument('feeds',type=Path)
  parser.add_argument('output',type=Path,help='New directory; never overwrite prior results')
  args=parser.parse_args();verify_weights(args.model)
  import onnxruntime as ort
  opts=ort.SessionOptions();opts.intra_op_num_threads=4;opts.inter_op_num_threads=1
  session=ort.InferenceSession(str(args.model),opts,providers=['CPUExecutionProvider'])
  with np.load(args.feeds,allow_pickle=False) as data:
    rows=run_sequence(session,{k:data[k] for k in data.files})
  args.output.mkdir(parents=True,exist_ok=False)
  np.savez_compressed(args.output/'raw-outputs.npz',outputs=np.stack([r['outputs'] for r in rows]))
  report=dict(inferenceExecuted=True,modelSha256=MODEL_SHA256,backend='ONNX Runtime CPU',
              frames=len(rows),initialState='zero',seconds=[r['seconds'] for r in rows],
              synchronizedCaptureProven=False,preprocessingValidated=False,
              gpuValidated=False,deviceActivated=False,actuationPermitted=False)
  (args.output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
  print(json.dumps({k:v for k,v in report.items() if k!='seconds'}))


if __name__=='__main__':main()
