"""Verify private ELF dependency closure and hashes; no inference or accuracy claim."""
import argparse,hashlib,json,struct
from pathlib import Path

SYSTEM={'libGLESv2.so','libEGL.so','libandroid.so','liblog.so','libz.so','libm.so','libdl.so','libc.so'}


def needed(binary):
  assert binary[:6]==b'\x7fELF\x02\x01' and struct.unpack_from('<H',binary,18)[0]==183
  off=struct.unpack_from('<Q',binary,40)[0];size,count=struct.unpack_from('<HH',binary,58)
  sections=[struct.unpack_from('<IIQQQQIIQQ',binary,off+i*size) for i in range(count)]
  result=[]
  for section in sections:
    if section[1]!=6:continue
    linked=sections[section[6]];strings=binary[linked[4]:linked[4]+linked[5]]
    for offset in range(section[4],section[4]+section[5],16):
      kind,value=struct.unpack_from('<qQ',binary,offset)
      if kind==1:result.append(strings[value:].split(b'\0',1)[0].decode())
  return result


def verify(root):
  libraries=root/'jniLibs/arm64-v8a'
  names={p.name for p in libraries.glob('*.so')}
  assert {'liblanenet.so','libVAE.so'}<=names
  for path in libraries.glob('*.so'):
    missing=set(needed(path.read_bytes()))-SYSTEM-names
    assert not missing,f'{path.name}: missing {sorted(missing)}'
  manifest=json.loads((root/'assets/cp-lane-assets.json').read_text())
  for name,digest in manifest['sha256'].items():
    path=root/(name.replace('lib/','jniLibs/',1) if name.startswith('lib/') else name)
    assert hashlib.sha256(path.read_bytes()).hexdigest()==digest,name
  print(json.dumps(dict(dependencyClosure=True,libraries=sorted(names),hashes=True)))


if __name__=='__main__':
  parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);verify(parser.parse_args().root)
