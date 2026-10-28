"""Actual upstream Kotlin client -> loopback-only Python receiver, plus the
upstream compact decoder. Synthetic payloads; no devices/route engines/models.
"""
from pathlib import Path
import argparse
import sys,json,time,subprocess,threading,select,base64,hashlib
from types import SimpleNamespace as N
parser=argparse.ArgumentParser();parser.add_argument('--build-dir',required=True,type=Path);parser.add_argument('--independent',action='store_true');args=parser.parse_args()
root=args.build_dir.resolve()
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'plugins'))
if args.independent:
 from cp_nav.cpserver import CPServer
 from cp_nav.ingress import CPStore
 from cp_nav.cpmeta import car_state_frame
 from cp_nav.engine import CPEngine
 from cp_nav.settings import CPSettings
else:
 from navassist.cpserver import CPServer
 from navassist.cpnav import CPStore
 from navassist.cpmeta import car_state_frame
config=json.loads((root/'run.json').read_text());base=[config['java'],'-cp',config['classpath'],'ProbeKt']
results=[]
for kind,expected in [('right','turn_right'),('sharp','sharp_left'),('exit','exit_right'),('model','turn_right')]:
 store=CPStore();server=CPServer(('127.0.0.1',0),store)
 worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
 p=subprocess.Popen([*base,kind,str(server.server_port)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 try:
  assert select.select([p.stdout],[],[],20)[0], 'Original CP client timed out before full session readiness'
  ready_line=p.stdout.readline();ready=json.loads(ready_line)
  assert ready['ready'] and ready['streams']==28
  end=time.monotonic()+2
  while time.monotonic()<end:
   if args.independent:
    snapshot=store.snapshot(connected=bool(server.owner and server.applied))
    if all(snapshot['items'].get(n,{}).get('present') for n in ('vehicle','guidance_current','route','navigation_status','lane_current')):break
    time.sleep(.01);continue
   nav=store.normalized(time.monotonic_ns())
   if nav['valid'] and ((kind=='model' and nav.get('modelLaneEstimate')) or (kind!='model' and nav['laneTotalCount']==3)):break
   time.sleep(.01)
  if args.independent:
   cs=N(vEgo=15.,aEgo=0.,speedLimit=0.,steeringPressed=False,steeringTorque=0.,gasPressed=False,
        brakePressed=False,vCruise=80.,vCruiseCluster=80.,gearShifter='drive',leftBlinker=False,
        rightBlinker=False,leftBlindspot=False,rightBlindspot=False)
   cc=N(enabled=True,latActive=True,longActive=True,cruiseControl=N(override=False))
   state=CPEngine(CPSettings(enabled=True)).update(snapshot,cs,cc,now_ns=time.monotonic_ns(),vehicle_fresh=True)
   assert state['valid'],(kind,state['reason'])
   assert snapshot['items']['guidance_current']['value']['turn_type']==ready['turn_type']
   lane=snapshot['items']['lane_current']['value']
   assert (lane['lane_source']=='model')==(kind=='model')
   results.append(dict(case=kind,ready=True,catalog=28,native_carrot_executed=True,
                       original_turn_type=ready['turn_type'],absolute_lane_permission=False))
  else:
   assert nav['valid'] and nav['maneuver']==expected,(kind,nav)
   if kind=='model':
    assert not nav['lanes'] and nav['laneTotalCount']==-1
    assert nav['modelLaneEstimate']['count']==5 and not nav['modelLaneEstimate']['mapAssociated']
   else:assert nav['laneTotalCount']==3 and nav['lanes'][2]['recommended'],(kind,nav)
   results.append(dict(case=kind,ready=True,catalog=28,enabled_json_streams=13,turn_type=ready['turn_type'],maneuver=nav['maneuver'],model_only_observation=kind=='model'))
 finally:
  if p.poll() is None:
   try:p.stdin.write('done\n');p.stdin.flush()
   except OSError:pass
  try:out,err=p.communicate(timeout=5)
  except subprocess.TimeoutExpired:p.kill();out,err=p.communicate()
  server.shutdown();server.server_close();worker.join(2)
  if p.returncode:raise RuntimeError(f'Original client failed: {p.returncode} {err[-1500:]}')
cs=N(vEgo=15.,aEgo=-.1,vEgoCluster=15.,vCruiseCluster=72.,steeringAngleDeg=1.5,
 gearShifter='drive',leftBlindspot=True,rightBlindspot=False,leftBlinker=False,rightBlinker=True)
packet=car_state_frame(cs,42)
r=subprocess.run([*base,'decode',base64.b64encode(packet).decode()],capture_output=True,text=True,timeout=10);assert r.returncode==0,r.stderr
frame=json.loads(r.stdout)['decoded'][0];values=frame['values']
assert frame['service']=='carState' and values['leftBlindspot'] is True and values['rightBlindspot'] is False and values['gearShifter']=='drive'
assert values['vEgo']==15. and values['rightBlinker'] is True
results.append(dict(case='original_compact_decoder',native_bsm=True,gear_and_speed=True,real_side_radar=False))
result=dict(independent_plugin=args.independent,source_commit=config['source_commit'],source_modified=False,compiled_original_sources=['NaviDataModels.kt','NaviWebSocketV2Client.kt','CompactStateDecoder.kt','AmapManeuver.kt'],cases=results,android_logging_shim=True,full_apk_build=False,mnn_executed=False,device_deployed=False,road_validated=False)
(root/('jvm-independent-interop-result.json' if args.independent else 'jvm-interop-result.json')).write_text(json.dumps(result,indent=2));print(json.dumps(result))
