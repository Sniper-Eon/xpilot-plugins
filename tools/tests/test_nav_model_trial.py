"""Failure cases before implementation: wrong/future/stale map or instruction,
route identity mismatch, disable, unqualified positioning, simulation, malformed
pixels and commands. Valid encoding must match pinned official helpers; revoke
must clear both inputs instead of holding an old map. Offline only, no actuation.
"""
import copy
import unittest
import numpy as np
from tools.nav_model_trial import build_inputs


class TrialContract(unittest.TestCase):
  def setUp(self):
    self.context = dict(session='s', revision=7, route='r')
    self.nav = dict(context=self.context.copy(), mono=10., valid=True, positioningQualified=True,
                    mode='realtime', maneuvers=[dict(type='turn', modifier='right', distance=100.)])
    self.frame = dict(context=self.context.copy(), mono=10., valid=True)
    self.image = np.full((256, 256), 128, dtype=np.uint8)

  def run_inputs(self, **kw):
    return build_inputs(self.nav, self.frame, self.image, now=10.1, speed=10., enabled=kw.get('enabled', True))

  def test_valid_distance_compensation(self):
    x, reason = self.run_inputs()
    self.assertEqual(reason, 'ready')
    self.assertEqual(x['nav_map'].shape, (1, 1, 256, 256))
    self.assertEqual(x['navigation'].dtype, np.float32)
    self.assertEqual(x['navigation'][0, 10], 1)
    self.assertAlmostEqual(float(x['navigation'][0, -1]), .99, places=5)

  def test_disable_clears(self):
    self.assertEqual(self.run_inputs(enabled=False)[0], {})

  def test_invalid_context_and_freshness(self):
    for target, field, value in [('nav','mono',8.), ('frame','mono',9.5), ('nav','mono',11.),
                                  ('frame','mono',11.), ('nav','valid',False), ('frame','valid',False),
                                  ('nav','positioningQualified',False), ('nav','mode','simulation')]:
      with self.subTest(target=target, field=field):
        old = copy.deepcopy(getattr(self,target)); getattr(self,target)[field] = value
        self.assertEqual(self.run_inputs()[0], {})
        setattr(self,target,old)
    for field in ('session','revision','route'):
      old = self.frame['context'][field]; self.frame['context'][field] = 'wrong'
      self.assertEqual(self.run_inputs()[0], {})
      self.frame['context'][field] = old

  def test_malformed_map_rejected(self):
    for image in [np.zeros((12,12),np.uint8), np.zeros((256,256),np.float32), None]:
      self.image=image; self.assertEqual(self.run_inputs()[0], {})

  def test_bad_commands_and_speed_rejected(self):
    for distance in [float('nan'),float('inf'),'100',True]:
      self.nav['maneuvers'][0]['distance']=distance
      self.assertEqual(self.run_inputs()[0], {})

  def test_invalid_speed(self):
    for speed in [-1, float("nan"), float("inf"), True, 101]:
      x,_=build_inputs(self.nav,self.frame,self.image,now=10.1,speed=speed,enabled=True)
      self.assertEqual(x,{})

  def test_merge_skipped_and_next_selected(self):
    self.nav['maneuvers']=[dict(type='merge',modifier='left',distance=20),
                           dict(type='off ramp',modifier='right',distance=200)]
    x,_=self.run_inputs(); self.assertEqual(x['navigation'][0,20],1)
    self.assertEqual(x['navigation'][0,15],0)

  def test_copy_no_feedback_and_no_held_inputs(self):
    x,_=self.run_inputs(); x['nav_map'][:]=0
    self.assertEqual(self.image[0,0],128)
    self.nav['valid']=False; self.assertEqual(self.run_inputs()[0],{})


if __name__ == '__main__':
  unittest.main()
