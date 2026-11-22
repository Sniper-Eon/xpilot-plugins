"""Real driving must never be authorized by a cached geometry object or a UI poll.

The existing v4 has no callback-based legacy navigation bridge. This check must
fail against v4 before implementing the bridge; packaging is separate from road
acceptance. Runtime cases are in LegacyNavigationHostTest.java.
"""
import os
import zipfile
from pathlib import Path
from test_callback_contract import dex_classes

APK = Path(os.environ['GEOMETRY_APK'])


def test_callback_navigation_bridge_packaged():
    with zipfile.ZipFile(APK) as z:
        classes = dex_classes(z.read('classes26.dex'))
        assert 'Lcom/marcus/tcprobe/geometry/LegacyNavigationTap;' in classes
        assert 'Lcom/marcus/tcprobe/geometry/NavigationObservations;' in classes
        assert all(x.startswith('Lcom/marcus/tcprobe/geometry/') for x in classes)
