"""Before implementation: portrait lacks the real Auto map; unready Auto hides SDK;
launch success is not pixels; detached/recreated surfaces must reconnect; no new
navigation source, freshness or vehicle-control behavior belongs in this UI fix.
Source checks accompany actual phone portrait/landscape/lifecycle rendering checks.
"""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]/'app/src'
NAV=ROOT/'main/kotlin/com/garan/tesnav/NavigationActivity.kt'
VIEW=ROOT/'tenengkai/kotlin/com/garan/tesnav/ui/EmbeddedAmapView.kt'
BRIDGE=ROOT/'tenengkai/kotlin/com/garan/tesnav/ui/EmbeddedAmapBridge.kt'

class MapViewContract(unittest.TestCase):
 def assertContains(self, text, source):
  self.assertTrue(text in source, f"Missing display contract: {text}")
 def test_both_orientations_share_the_actual_embedded_map_layer(self):
  s=NAV.read_text()
  self.assertContains('private fun createMapPane()',s)
  self.assertGreaterEqual(s.count('createMapPane()'),3)
  self.assertEqual(s.count('EmbeddedAmapView(this'),1)
 def test_source_selection_cannot_hide_a_map_without_real_frames(self):
  s=NAV.read_text()
  self.assertNotIn('splitMapPane?.visibility = if (autoSelected) View.INVISIBLE',s)
  self.assertContains('onAvailabilityChanged =',s)
  self.assertContains('if (ready) View.INVISIBLE else View.VISIBLE',s)
 def test_launch_acceptance_cannot_hide_the_loading_state(self):
  s=VIEW.read_text()
  self.assertContains('private var frameReceived = false',s)
  self.assertContains('private var displayVerified = false',s)
  self.assertContains('displayVerified && frameReceived',s)
  self.assertContains('override fun onSurfaceTextureUpdated',s)
  self.assertNotIn('override fun onSurfaceTextureUpdated(surface: SurfaceTexture) = Unit',s)
 def test_attach_restores_the_existing_navigation_opener(self):
  s=VIEW.read_text().split('override fun onAttachedToWindow()',1)[1].split('override fun onDetachedFromWindow()',1)[0]
  self.assertContains('AmapAutoActions.embeddedOpener = embeddedOpener',s)
 def test_all_build_types_support_the_readiness_contract(self):
  for flavor in ('debug','release','tenengkai'):
   s=(ROOT/f'{flavor}/kotlin/com/garan/tesnav/ui/EmbeddedAmapView.kt').read_text()
   self.assertContains('onAvailabilityChanged',s)
 def test_launch_verifies_the_actual_target_display(self):
  self.assertContains('return current == display',BRIDGE.read_text())
  self.assertTrue('childTaskNames' in BRIDGE.read_text(), 'Android RootTaskInfo uses childTaskNames, not legacy taskNames')

if __name__=='__main__':unittest.main()
