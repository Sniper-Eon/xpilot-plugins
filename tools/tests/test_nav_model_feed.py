"""Before implementation: reject mismatched camera/request counts and stale maps;
withdrawn optional inputs must be zero on that frame, not retain last good image.
This is offline recorded-envelope ingestion, not a live phone/SDK integration.
"""
import unittest
import numpy as np
from tools.nav_model_feed import prepare_feeds

class FeedContract(unittest.TestCase):
  def test_stream_withdrawal(self):
    c=dict(session='s',revision=1,route='r')
    r=dict(nav=dict(context=c,mono=10.,valid=True,positioningQualified=True,mode='realtime',
                    maneuvers=[dict(type='turn',modifier='right',distance=100)]),
           frame=dict(context=c,mono=10.,valid=True),now=10.1,speed=10.,enabled=True)
    data={'new_img':np.zeros((2,2,6,128,256),np.uint8),
          'desire':np.zeros((2,8),np.float32),
          'traffic_convention':np.zeros((2,1,2),np.float32),
          'action_t':np.ones((2,1,2),np.float32)}
    rows=[r,dict(r,enabled=False)]
    x,reasons=prepare_feeds(data,rows,lambda r:np.full((256,256),128,np.uint8))
    self.assertEqual(reasons,['ready','disabled'])
    self.assertEqual(x['navigation'][0,0,10],1)
    self.assertFalse(x['navigation'][1].any());self.assertFalse(x['nav_map'][1].any())
    with self.assertRaises(ValueError):prepare_feeds(data,rows[:1],lambda r:None)

if __name__=='__main__':unittest.main()
