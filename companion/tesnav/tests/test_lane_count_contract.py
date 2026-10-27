"""Failure cases: legacy declared width survives normalized padding removal;
empty lane callbacks preserve a declared count; count and lane items disagree on
export. This source-boundary check complements SDK-free Kotlin wire replay tests.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'app/src/main/kotlin/com/garan/tesnav'

class LaneCountContract(unittest.TestCase):
    def test_legacy_callback_publishes_normalized_count_with_its_lane_list(self):
        source = (ROOT / 'data/NavigationRepository.kt').read_text()
        callback = source.split('override fun showLaneInfo(laneInfos:', 1)[1].split(
            'override fun showLaneInfo(laneInfo:', 1)[0]
        update = callback.split('update {', 1)[1]
        self.assertRegex(update, r'lanes\s*=\s*lanes,')
        self.assertRegex(update, r'laneCount\s*=\s*(?:count|lanes.size)\.takeIf\s*\{\s*it in 1\.\.16\s*\}')
        self.assertNotIn('laneInfos?.firstOrNull()?.laneCount', update)

if __name__ == '__main__':
    unittest.main()
