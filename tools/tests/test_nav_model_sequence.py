"""Failure cases before implementation: wrong weights must never create a session;
next-state must advance each frame, malformed/nonfinite outputs must stop replay,
and invalid frame feeds must not run. Fixture sessions are NOT driving evidence.
"""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as N
import numpy as np
from tools.nav_model_sequence import run_sequence, verify_weights

class Session:
  def __init__(self, bad=False):self.bad=bad;self.calls=0
  def get_inputs(self):return [N(name='new_img',shape=[1],type='tensor(uint8)'),N(name='state_q',shape=[1],type='tensor(float)')]
  def get_outputs(self):return [N(name='outputs'),N(name='next_state_q')]
  def run(self,names,feed):
    self.calls+=1
    return [feed['state_q']+feed['new_img'],np.array([np.nan],np.float32) if self.bad else feed['state_q']+1]

class Contract(unittest.TestCase):
  def test_weight_mismatch(self):
    with TemporaryDirectory() as d:
      p=Path(d)/'bad.onnx';p.write_bytes(b'wrong')
      with self.assertRaises(ValueError):verify_weights(p)
  def test_state_carries(self):
    rows=run_sequence(Session(),{'new_img':np.ones((3,1),np.uint8)})
    self.assertEqual([r['outputs'][0] for r in rows],[1,2,3])
  def test_nan_stops(self):
    with self.assertRaises(ValueError):run_sequence(Session(True),{'new_img':np.ones((3,1),np.uint8)})
  def test_bad_feed_stops_before_session(self):
    s=Session()
    with self.assertRaises(ValueError):run_sequence(s,{'new_img':np.ones((3,1),np.float32)})
    self.assertEqual(s.calls,0)

if __name__=='__main__':unittest.main()
