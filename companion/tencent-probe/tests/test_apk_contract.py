import os
import re
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APK = Path(os.environ.get('GEOMETRY_APK', Path(os.environ['TENCENT_BASE_APK'])))
JAVA = '/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home'


def test_application_boots_geometry_exporter():
    env = dict(os.environ, JAVA_HOME=JAVA)
    xml = subprocess.check_output(['/opt/homebrew/bin/apkanalyzer', 'manifest', 'print', str(APK)], env=env, text=True)
    assert 'android:name="com.marcus.tcprobe.geometry.GeometryProbeApp"' in xml
    assert 'package="com.tencent.map"' in xml


def test_added_dex_preserves_original_payloads():
    base = Path(os.environ['TENCENT_BASE_APK'])
    with zipfile.ZipFile(base) as a, zipfile.ZipFile(APK) as b:
        extra = {name for name in set(b.namelist()) - set(a.namelist())
                 if not re.fullmatch(r'META-INF/[^/]+\.(SF|RSA|DSA|EC|MF)',name,re.I)}
        assert extra == {'classes26.dex'}
        assert b'com/marcus/tcprobe/geometry/GeometryProbeApp' in b.read('classes26.dex')
        for name in a.namelist():
            if name == 'AndroidManifest.xml' or re.fullmatch(r'META-INF/[^/]+\.(SF|RSA|DSA|EC|MF)', name, re.I):
                continue
            assert a.read(name) == b.read(name), name
