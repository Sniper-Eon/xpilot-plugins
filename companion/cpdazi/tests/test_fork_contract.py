"""Pre-implementation source contracts for the CP-derived companion candidate."""
from pathlib import Path
import json
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ForkContract(unittest.TestCase):
    def test_source_identity_is_honest(self):
        data = json.loads((ROOT / 'PROVENANCE.json').read_text())
        self.assertEqual(data['upstream_commit'], '3f1af5f50bfb3c414aa40b9ab48a2fe6cf5afbda')
        self.assertFalse(data['matches_supplied_8_0_20'])

    def test_cancelled_controller_is_absent(self):
        sources = list((ROOT / 'app/src/main').rglob('*.kt'))
        self.assertGreater(len(sources), 20)
        for path in sources:
            text = path.read_text()
            self.assertNotIn('AutoOvertakeManager', text, str(path))
            self.assertNotIn('overtake_mode', text, str(path))

    def test_update_identity_and_label(self):
        build = (ROOT / 'app/build.gradle.kts').read_text()
        self.assertIn('applicationId = "com.garan.tesnav.tenengkai.lane"', build)
        self.assertIn('LANETEST_STORE_FILE', build)
        for path in (ROOT / 'app/src/main/res').glob('values*/strings.xml'):
            self.assertIn('X-Pilot CP导航', path.read_text(), str(path))

    def test_no_unrequested_vehicle_defaults(self):
        self.assertFalse((ROOT / 'app/src/main/res/raw/config.json').exists())

    def test_no_upstream_signing_material(self):
        self.assertFalse((ROOT / 'app/release.keystore').exists())
        self.assertFalse((ROOT / 'local.properties').exists())


if __name__ == '__main__':
    unittest.main()
