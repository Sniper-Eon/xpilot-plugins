"""Build a diagnostic APK candidate. Never installs or changes a device.

Failure contract: absent cache stays unknown; preserve 64-bit lane IDs; cap object
graphs; preserve original DEX/native/resources; verify the Application entry.
The reader polls HDMonitor and appends an observer to the existing map manager.
"""
import argparse
import hashlib
import json
import os
import re
import struct
import subprocess
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE
OLD_APP = 'com.marcus.tcprobe.TcProbeApp'
NEW_APP = 'com.marcus.tcprobe.geometry.GeometryProbeApp'


def length8(n):
    if n >= 32768:
        raise ValueError('AXML UTF8 length exceeds two-byte format')
    return bytes([n]) if n < 128 else bytes([128 | (n >> 8), n & 255])


def patch_manifest(data):
    """Replace one string-pool entry, keeping resource references and indices."""
    assert struct.unpack_from('<H', data)[0] == 3
    pos = struct.unpack_from('<H', data, 2)[0]
    while pos < len(data):
        kind, header, size = struct.unpack_from('<HHI', data, pos)
        if kind != 1:
            pos += size
            continue
        chunk = data[pos:pos+size]
        count, styles, flags, start, style_start = struct.unpack_from('<5I', chunk, 8)
        offsets = struct.unpack_from('<'+'I'*count, chunk, header)
        strings = []
        replaced = 0
        for offset in offsets:
            p = start + offset
            origin = p
            if flags & 256:
                n = chunk[p]; p += 1
                if n & 128:
                    n = ((n & 127) << 8) | chunk[p]; p += 1
                n = chunk[p]; p += 1
                if n & 128:
                    n = ((n & 127) << 8) | chunk[p]; p += 1
                text = chunk[p:p+n].decode('utf-8')
                end = p+n+1
                if text == OLD_APP:
                    raw = NEW_APP.encode('utf-8')
                    strings.append(length8(len(NEW_APP))+length8(len(raw))+raw+b'\0')
                    replaced += 1
                else:
                    strings.append(chunk[origin:end])
            else:
                n = struct.unpack_from('<H', chunk, p)[0]; p += 2
                if n & 32768:
                    n = ((n & 32767) << 16) | struct.unpack_from('<H', chunk, p)[0]; p += 2
                text = chunk[p:p+n*2].decode('utf-16le')
                end = p+n*2+2
                if text == OLD_APP:
                    strings.append(struct.pack('<H',len(NEW_APP))+NEW_APP.encode('utf-16le')+b'\0\0')
                    replaced += 1
                else:
                    strings.append(chunk[origin:end])
        assert replaced == 1, ('unexpected Application string matches', replaced)
        content = bytearray(); new_offsets = []
        for raw in strings:
            new_offsets.append(len(content)); content.extend(raw)
        content.extend(b'\0'*(-len(content) % 4))
        h = bytearray(chunk[:header])
        tables = struct.pack('<'+'I'*count, *new_offsets)+chunk[header+4*count:header+4*(count+styles)]
        new_start = len(h)+len(tables)
        style_data = chunk[style_start:] if styles else b''
        new_style_start = new_start+len(content) if styles else 0
        new_size = new_start+len(content)+len(style_data)
        struct.pack_into('<I',h,4,new_size)
        struct.pack_into('<III',h,16,flags & ~1,new_start,new_style_start)
        updated = data[:pos]+bytes(h)+tables+bytes(content)+style_data+data[pos+size:]
        updated = bytearray(updated); struct.pack_into('<I',updated,4,len(updated))
        return bytes(updated)
    raise ValueError('AXML has no string pool')


def run(args, env):
    subprocess.run([str(a) for a in args], env=env, check=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--base',type=Path,required=True)
    p.add_argument('--keystore',type=Path,default=Path.home()/'.android/debug.keystore')
    args=p.parse_args()
    java=Path('/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home')
    sdk=Path(os.environ.get('ANDROID_HOME',str(Path.home()/'Library/Android/sdk')))
    tools=sdk/'build-tools/37.0.0'
    env=dict(os.environ,JAVA_HOME=str(java))
    build=HERE/'build'; build.mkdir(exist_ok=True)
    classes=build/'classes'; classes.mkdir(exist_ok=True)
    out=ROOT/'out'; out.mkdir(exist_ok=True)
    sources=sorted((HERE/'src').rglob('*.java'))+sorted((HERE/'stubs').rglob('*.java'))
    run([java/'bin/javac','-source','8','-target','8','-classpath',sdk/'platforms/android-37.0/android.jar','-d',classes,*sources],env)
    dex=build/'dex'; dex.mkdir(exist_ok=True)
    # The compile-time superclass stub must never replace the original app.
    production=sorted((classes/'com/marcus/tcprobe/geometry').glob('*.class'))
    stubjar=build/'compiler-stub.jar'
    run([java/'bin/jar','cf',stubjar,'-C',classes,'com/marcus/tcprobe/TcProbeApp.class','-C',classes,'com/tencent'],env)
    run([tools/'d8','--min-api','21','--lib',sdk/'platforms/android-37.0/android.jar','--classpath',stubjar,'--output',dex,*production],env)
    unsigned=build/'geometry-unsigned.apk'
    removed=[]
    with zipfile.ZipFile(args.base) as src, zipfile.ZipFile(unsigned,'w') as dest:
        assert 'classes26.dex' not in src.namelist()
        for info in src.infolist():
            if re.fullmatch(r'META-INF/[^/]+\.(SF|RSA|DSA|EC|MF)',info.filename,re.I):
                removed.append(info.filename); continue
            data=src.read(info.filename)
            if info.filename=='AndroidManifest.xml':data=patch_manifest(data)
            dest.writestr(info,data)
        dest.write(dex/'classes.dex','classes26.dex',compress_type=zipfile.ZIP_DEFLATED)
    aligned=build/'geometry-aligned.apk'
    run([tools/'zipalign','-P','16','-f','4',unsigned,aligned],env)
    signed=out/'tc-v61-navigation-observer-v5.apk'
    run([tools/'apksigner','sign','--ks',args.keystore,'--ks-key-alias','androiddebugkey','--ks-pass','pass:android','--key-pass','pass:android','--out',signed,aligned],env)
    run([tools/'apksigner','verify','--verbose',signed],env)
    run([tools/'zipalign','-P','16','-c','4',signed],env)
    with zipfile.ZipFile(args.base) as a,zipfile.ZipFile(signed) as b:
        checked=0
        for name in a.namelist():
            if name=='AndroidManifest.xml' or name in removed:continue
            assert hashlib.sha256(a.read(name)).digest()==hashlib.sha256(b.read(name)).digest(),name
            checked+=1
    metadata=dict(candidate=str(signed.relative_to(ROOT)),sha256=hashlib.sha256(signed.read_bytes()).hexdigest(),
        unchanged_original_entries=checked,application=NEW_APP,added_dex='classes26.dex',
        feature='append legacy navigation, position and HD callbacks; retain bounded geometry diagnostics',
        endpoints=['loopback ports 8898..8907: /health, /geometry, /navigation'],
        sourceFreshness='unknown_cached_object',coordinateSystem='unknown_raw',controlUsable=False,
        device_installed=False,live_geometry_obtained=False)
    (out/'build-result.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(metadata,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
