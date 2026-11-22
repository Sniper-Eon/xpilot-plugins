"""Failures: cache-only APK misses GuideLine callbacks; SDK stubs must not replace real classes."""
import os
import struct
import zipfile
from pathlib import Path

BASE = Path(os.environ['GEOMETRY_APK'])
APK = Path(os.environ.get('GEOMETRY_APK', str(BASE)))


def dex_classes(data):
    def u(p):
        return struct.unpack_from('<I', data, p)[0]
    strings = []
    for i in range(u(56)):
        p = u(u(60)+4*i)
        while data[p] & 128:
            p += 1
        p += 1
        strings.append(data[p:data.index(b'\0', p)].decode('utf8', 'replace'))
    types = [strings[u(u(68)+4*i)] for i in range(u(64))]
    return {types[u(u(100)+32*i)]: types[u(u(100)+32*i+8)] for i in range(u(96))}


def test_appended_listener_is_packaged_without_sdk_stubs():
    with zipfile.ZipFile(APK) as z:
        classes = dex_classes(z.read('classes26.dex'))
        name = 'Lcom/marcus/tcprobe/geometry/GeometryCallbacks;'
        assert classes.get(name) == 'Lcom/tencent/pangu/mapbiz/MapBizEventListener;'
        assert all(name.startswith('Lcom/marcus/tcprobe/geometry/') for name in classes)


def test_route_inspector_is_packaged():
    with zipfile.ZipFile(APK) as z:
        classes = dex_classes(z.read('classes26.dex'))
        assert 'Lcom/marcus/tcprobe/geometry/RouteDataInspector;' in classes
