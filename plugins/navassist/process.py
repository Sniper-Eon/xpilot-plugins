"""One NavAssist process: source-compatible ingress and bounded plugin messages.

No VisionIPC camera client, JPEG encoder, steering or acceleration publisher.
"""
from __future__ import annotations

import time

from openpilot.cereal import messaging
from openpilot.common.params import Params
from openpilot.common.realtime import Ratekeeper
from openpilot.common.swaglog import cloudlog
from openpilot.tesla import plugins

from .can_input import can_batches
from .closingd import read_packet
from .network import NavigationTransports
from .phone import PhoneBlindspotAssist
from .plugin import NavAssist
from .position import publish as publish_position
from .recording import Recorder
from .runtime import NavigationRuntime
from .settings import read as read_settings
from .store import NavAssistStore

PUBLISH_HZ = 20
REPLAY_CHECKPOINT_PATH = '/dev/shm/xpilot_navassist_replay_state.json'


def healthy(sm, names, now_ns, limit_ns=250_000_000):
  return all(sm.seen[n] and sm.alive[n] and sm.valid[n] and 0 <= now_ns-sm.logMonoTime[n] <= limit_ns for n in names)


def main():
  params = plugins.view(Params())
  settings = read_settings(params)
  runtime = NavigationRuntime(settings)
  store = NavAssistStore(checkpoint_path=REPLAY_CHECKPOINT_PATH)
  sm = messaging.SubMaster(['modelV2', 'carState', 'carControl', 'controlsState', 'deviceState', 'deviceMotion'])
  can_socket = messaging.sub_sock('can', conflate=False)
  pm = messaging.PubMaster(['pluginMsg'])
  state = {'offroad': False}
  transports = NavigationTransports(store, params, lambda: state['offroad'])
  phone = PhoneBlindspotAssist(mode='assist' if settings.phone_assist_enabled else 'shadow')
  recorder = Recorder()
  rk = Ratekeeper(PUBLISH_HZ)
  next_settings = next_record = 0
  cloudlog.info('xpilot NavAssist transports online')
  try:
    while True:
      sm.update(0)
      now = time.monotonic_ns()
      state['offroad'] = bool(sm.alive['deviceState'] and sm.valid['deviceState']
                              and not sm['deviceState'].started and params.get_bool('IsOffroad'))
      if now >= next_settings:
        next_settings = now+1_000_000_000
        settings = read_settings(params)
        runtime.settings = settings
        phone.mode = 'assist' if settings.phone_assist_enabled else 'shadow'
        if state['offroad'] and params.get_bool('ExtNavAssistPairingReset'):
          transports.pairing.reset()
          params.put_bool('ExtNavAssistPairingReset', False)
      model_good = healthy(sm, ['modelV2'], now, 150_000_000)
      model = sm['modelV2'] if model_good else None
      phone_sides = phone.read(now) if phone.enabled else None
      vehicle_fresh = healthy(sm, ['carState', 'carControl', 'controlsState'], now)
      pose_ok = healthy(sm, ['deviceMotion'], now, 500_000_000) and sm['deviceMotion'].inputsOK
      cs, cc = sm['carState'], sm['carControl']
      curvature = float(sm['controlsState'].desiredCurvature) if vehicle_fresh else 0.
      result = runtime.tick(store.current(now), model, int(sm.logMonoTime['modelV2']), cs, cc, now,
        can_list=can_batches(messaging.drain_sock(can_socket)), vehicle_fresh=vehicle_fresh,
        left_phone=bool(phone_sides and phone_sides[0].blocked), right_phone=bool(phone_sides and phone_sides[1].blocked),
        phone_packet=read_packet(), turn_geometry_active=cs.vEgo**2*abs(curvature) >= 1.1,
        localization_valid=bool(pose_ok))
      publish_position(result['position'])
      for key, kind, ttl in [('nav', 'nav.state', 1000), ('topology', 'lanes.topology', 150),
                            ('intent', 'lanes.intent', 200), ('oem', 'oem.lanes', 500),
                            ('closing', 'vision.closing', 800)]:
        plugins.send_msg(pm, NavAssist, kind, result[key], ttl)
      if now >= next_record:
        next_record = now+100_000_000
        recorder.write(dict(kind='sample', wall_time_ms=time.time_ns()//1_000_000,
                            mono_time_ns=now, **result))
      rk.keep_time()
  finally:
    recorder.close()
    transports.close()
    publish_position(dict(version=1, valid=False, absolute_confirmed=False, capture_mono_ns=time.monotonic_ns()))


if __name__ == '__main__':
  main()
