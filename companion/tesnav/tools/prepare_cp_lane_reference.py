"""Extract an explicitly supplied user's CP APK into a LOCAL build input directory.
Never downloads or publishes reference assets. Output must be outside the Git tree.
"""
import argparse,hashlib,json,zipfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--apk',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
a=p.parse_args();root=Path(__file__).resolve().parents[3]
assert not a.output.resolve().is_relative_to(root),'keep private assets outside plugin repository'
assert not a.output.exists(),'refuse to overwrite reference assets'
files=['lib/arm64-v8a/liblanenet.so','lib/arm64-v8a/libVAE.so','lib/arm64-v8a/libthird_party_libs.so','lib/arm64-v8a/libbase_utils.so','assets/models/vlaneDay.mnn','assets/models/vlaneNight.mnn']
hashes={}
with zipfile.ZipFile(a.apk) as z:
 for name in files:
  data=z.read(name);assert data
  dest=a.output/(name.replace('lib/','jniLibs/',1) if name.startswith('lib/') else name)
  dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data);hashes[name]=hashlib.sha256(data).hexdigest()
manifest=dict(source_apk_sha256=hashlib.sha256(a.apk.read_bytes()).hexdigest(),sha256=hashes,local_only=True)
(a.output/'assets/cp-lane-assets.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(manifest))
