"""Compile unmodified CP navigation client/mapper/decoder for loopback interop.
Failures: wrong snapshot, mutated source, unavailable compiler or declared JVM
libraries. Android Log is the only shim; no video/model/UI/vehicle code executes.
This is a JVM interoperability probe, not an Android APK build.
"""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,urllib.request
PIN='91d77de4fd7650ebc76c38cf4b47ede503f6d0dc'
a=argparse.ArgumentParser();a.add_argument('source',type=Path);a.add_argument('--output',required=True,type=Path);args=a.parse_args()
source=args.source.resolve();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()==PIN,'wrong source snapshot'
cache=Path(os.environ.get('GRADLE_USER_HOME',str(Path.home()/'.gradle')))/'caches/modules-2/files-2.1'
def jar(group,name,version):return str(next((cache/group/name/version).glob('*/*.jar')))
std=jar('org.jetbrains.kotlin','kotlin-stdlib','2.1.0')
compiler=[jar('org.jetbrains.kotlin','kotlin-compiler-embeddable','2.1.0'),std,jar('org.jetbrains.kotlin','kotlin-script-runtime','2.1.0'),jar('org.jetbrains.intellij.deps','trove4j','1.0.20200330'),jar('org.jetbrains','annotations','13.0'),jar('org.jetbrains.kotlinx','kotlinx-coroutines-core-jvm','1.6.4')]
jsonjar=out/'json-20240303.jar'
if not jsonjar.exists():jsonjar.write_bytes(urllib.request.urlopen('https://repo.maven.apache.org/maven2/org/json/json/20240303/json-20240303.jar',timeout=30).read())
deps=[std,jar('org.jetbrains','annotations','13.0'),jar('org.jetbrains.kotlinx','kotlinx-coroutines-core-jvm','1.7.3'),jar('com.squareup.okhttp3','okhttp','4.12.0'),jar('com.squareup.okio','okio-jvm','3.6.0'),str(jsonjar)]
base=source/'app/src/main/java/com/jixiexiaoge/drivingassist'
originals=[base/'navigation/NaviDataModels.kt',base/'navigation/NaviWebSocketV2Client.kt',base/'data/CompactStateDecoder.kt',base/'AmapManeuver.kt']
hashes={}
for p in originals:
 raw=p.read_bytes();tracked=subprocess.check_output(['git','show',f'{PIN}:{p.relative_to(source)}'],cwd=source)
 assert raw==tracked,f'modified upstream source: {p.name}'
 hashes[str(p.relative_to(source))]=hashlib.sha256(raw).hexdigest()
java=str(Path(os.environ['JAVA_HOME'])/'bin/java') if 'JAVA_HOME' in os.environ else shutil.which('java')
assert java,'Set JAVA_HOME to a working JDK17+'
local=Path(__file__).resolve().parent
cmd=[java,'-cp',':'.join(compiler),'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler','-no-stdlib','-no-reflect','-jvm-target','17','-classpath',':'.join(deps),'-d',str(out/'probe.jar')]+list(map(str,[*originals,local/'Log.kt',local/'Probe.kt']))
subprocess.run(cmd,check=True)
(out/'run.json').write_text(json.dumps(dict(java=java,classpath=':'.join([str(out/'probe.jar'),*deps]),source_commit=PIN,source_hashes=hashes)))
print('Original CP client/mapper/models/compact decoder compiled; no APK or MNN execution.')
