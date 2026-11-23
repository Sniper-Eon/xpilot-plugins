"""Existing navigation log formatting; no control outputs."""
from . import gpsfeed


def record_cycle(result, cs, cc, model, model_good, now, lat_diag, state):
  try:
    _i = result['intent']
    _n = result['nav']
    _lanes = _n.get('lanes') or ()
    _topo = result.get('topology') or {}
    _ego = int(_topo.get('egoLaneIndexFromLeft', -1) or -1)
    _cnt = int(_topo.get('visibleLaneCount', 0) or 0)
    _key = (bool(_n.get('valid')), bool(_n.get('linked')), bool(_n.get('routeActive')),
            str(_n.get('maneuver')), int(_n.get('maneuverEventId') or 0),
            float(_n.get('distanceM') or 0.0), float(getattr(cs, 'vEgo', 0.0)),
            len(_lanes), sum(1 for _l in _lanes if _l.get('recommended') is True), _ego, _cnt,
            bool(_i.get('signalRequested')), str(_i.get('direction')),
            str(_i.get('reason')), int(_i.get('targetLaneIndex', -1)),
            bool(cs.leftBlinker), bool(cs.rightBlinker), bool(cc.latActive),
            str(getattr(model.meta, 'laneChangeState', 'na')) if model_good else 'na')
    import time as _t
    _now_s = _t.monotonic()
    _due = (_now_s - state.get('_last_fnav_log', 0.0)) >= 1.0
    if _key != state.get('_last_key') or _due:
      state['_last_key'] = _key
      if _due:
        state['_last_fnav_log'] = _now_s
      _LOG_PATH = '/data/log/navassist-lane.log'
      try:
        import os as _os, time as _time
        _now = _time.monotonic()
        if _now - state.get('_last_disk_check', 0.0) > 60.0:
          state['_last_disk_check'] = _now
          _st = _os.statvfs('/data')
          _free = _st.f_bavail * _st.f_frsize
          _total = _st.f_blocks * _st.f_frsize
          # 剩余空间低于 10% 时覆盖旧日志，避免把磁盘写满。
          if _total > 0 and _free / _total < 0.10 and _os.path.exists(_LOG_PATH):
            with open(_LOG_PATH, 'w'):
              pass
      except Exception:
        pass
      with open(_LOG_PATH, 'a') as _f:
        if not state.get('_fnav_header_written'):
          _f.write('# fnav v1 junction_side=fused gps_jump=0 route_offset=road_centre width_default=3.4\n')
          state['_fnav_header_written'] = True
        _ovt = ((result.get('nav') or {}).get('overtake') or {})
        # 日志在灯诊断写入之前，直接读 card 进程落盘的文件，否则永远是 -/-
        _lamp = {}
        try:
          import json as _jl
          with open('/tmp/navassist_lamp.json') as _lf:
            _lamp = _jl.load(_lf)
        except Exception:
          _lamp = {}
        _flags = ('B' if getattr(cs, 'brakePressed', False) else '-') + \
                 ('G' if getattr(cs, 'gasPressed', False) else '-') + \
                 ('S' if getattr(cs, 'steeringPressed', False) else '-')
        _topo = result.get('topology') or {}
        _abs = _topo.get('absoluteEgoIndex')
        _abs_src = _topo.get('absoluteSource') or ('phone' if _topo.get('phoneLaneCount') else '-')
        _recset = '{' + ','.join(str(_l.get('index')) for _l in (_n.get('lanes') or [])
                                 if _l.get('recommended') is True) + '}'
        # 左右阻塞原因（来自 blocker.update 的第三个返回值）
        _ev_vis = ((result.get('nav') or {}).get('phoneLaneEvidence') or {})
        if _ev_vis.get('valid'):
          _vis = '%s/%s@%s' % (_ev_vis.get('laneNumber'), _ev_vis.get('laneCount'), _ev_vis.get('samples'))
        else:
          _vis = '-'
        _road = '%s/%s' % ((result.get('road_kind') or '-'), (result.get('road_name') or '-'))
        _old = '%s/%s' % ('-' if result.get('old_abs') is None else result.get('old_abs'),
                          result.get('old_src') or '-')
        _spd = '-'
        try:
          import json as _json
          with open('/tmp/navassist_speed.json') as _f2:
            _sp = _json.load(_f2)
          _out = _sp.get('output')
          _spd = '%s/%s@%s' % ('-' if _out is None else round(float(_out) * 3.6),
                               round(float(_sp.get('target') or 0) * 3.6), _sp.get('maneuver', '-'))
        except Exception:
          _spd = '-'
        _tp = result.get('topology') or {}
        try:
          _v = _tp.get('estimateValue')
          _est = '%s/%s/%.2f' % ('-' if _v is None else _v,
                                 _tp.get('estimateSource') or '-',
                                 float(_tp.get('estimateConfidence') or 0.0))
        except Exception:
          _est = '-'
        try:
          _alc_txt = '%s/%d' % ((result.get('oem') or {}).get('alcName', '-'),
                               1 if (result.get('oem') or {}).get('alcFresh') else 0)
        except Exception:
          _alc_txt = '-'
        try:
          _acc = gpsfeed.accuracy_m(now)
          _gps_txt = '-' if _acc is None else round(float(_acc), 1)
        except Exception:
          _gps_txt = '-'
        try:
          _gv = _tp.get('geoValue')
          _geo_txt = '%s/%.2f/%s' % ('-' if _gv is None else _gv,
                                     float(_tp.get('geoConfidence') or 0.0),
                                     _tp.get('geoReason') or '-')
        except Exception:
          _geo_txt = '-'
        try:
          _d = lat_diag.get('offsetM')
          _w = lat_diag.get('widthM')
          _off = '%s/%s' % ('-' if _d is None else _d, '-' if not _w else round(float(_w), 1))
        except Exception:
          _off = '-/-'
        try:
          _edge = 'L%d%d/R%d%d' % (
            1 if _tp.get('leftEdgeDetected') else 0,
            1 if _tp.get('leftCarriagewayAnchored') else 0,
            1 if _tp.get('rightEdgeDetected') else 0,
            1 if _tp.get('rightCarriagewayAnchored') else 0)
          _edge += '@%d/%d' % (int(_tp.get('leftEdgeGapM', 99) or 99), int(_tp.get('rightEdgeGapM', 99) or 99))
        except Exception:
          _edge = '-'
        _blk = '-'
        try:
          _rs = (result.get('oem') or {}).get('blockReasons') or ()
          if len(_rs) == 2:
            _blk = '%s|%s' % ((_rs[0] or '-'), (_rs[1] or '-'))
        except Exception:
          _blk = '-'
        if _recset == '{}':
          _recset = '-'
        try:
          _v3l = (result.get('topology') or {}).get('laneV3') or {}
          if _v3l.get('err'):
            _v3_txt = 'err:' + str(_v3l.get('err'))
          elif _v3l:
            _v3_txt = ('%s/%s/%s%s' % ('-' if _v3l.get('value') is None else _v3l.get('value'),
                       _v3l.get('state', '-'), _v3l.get('reason', '-'),
                       '/prov' if _v3l.get('provisional') else '')).replace(' ', '_')
          else:
            _v3_txt = '-'
        except Exception:
          _v3_txt = '-'
        try:
          _fn = (result.get('topology') or {}).get('fnav') or {}
          _bel = _fn.get('belief') or ()
          _fnav = '%s/%s/%s/%s{%s}' % (
            '-' if _fn.get('lane1') is None else _fn.get('lane1'),
            '-' if _fn.get('n') is None else _fn.get('n'),
            '-' if _fn.get('prob') is None else _fn.get('prob'),
            _fn.get('reason') or '-',
            ','.join('%.2f' % float(x) for x in _bel) if _bel else '-')
          if _fn.get('err'):
            _fnav = 'err:' + str(_fn.get('err'))
          _side = '-'
          if _fn.get('side_added') is not None:
            _why = _fn.get('side_why') or ()
            _side = '%s@%s%s%s' % (
              _fn.get('side_added'), _fn.get('side_conf', '-'),
              (':' + ','.join(str(x) for x in _why)) if _why else '',
              '' if _fn.get('side_final') in (None, True) else '/tmp')
          _dr = '-' if _fn.get('dr_lat') is None else _fn.get('dr_lat')
        except Exception:
          _fnav, _side, _dr = '-', '-', '-'
        try:
          _yaw_txt = '-' if lat_diag.get('yaw') is None else ('%s@%s' % (lat_diag.get('yaw'), lat_diag.get('yawSrc') or '-'))
          _hdg_txt = '-' if lat_diag.get('bearing') is None else round(float(lat_diag['bearing']), 1)
          _rte_txt = '-' if lat_diag.get('route_bearing') is None else round(float(lat_diag['route_bearing']), 1)
          if lat_diag.get('lat') is None or lat_diag.get('lon') is None:
            _ll_txt = '-'
          else:
            _ll_txt = '%.6f,%.6f' % (float(lat_diag['lat']), float(lat_diag['lon']))
        except Exception:
          _yaw_txt, _hdg_txt, _rte_txt, _ll_txt = '-', '-', '-', '-'
        try:
          _ro = (result.get('topology') or {}).get('holdRoadRecording') or {}
          _obs_txt = '%s/%s/%s:%s%s' % (
            _ro.get('step', -1), _ro.get('link', -1), _ro.get('point', -1),
            _ro.get('recommendationAction', '-'), '/chg' if _ro.get('linkChanged') else '')
        except Exception:
          _obs_txt = '-/-/-:-'
        _f.write('%.1f v=%d lk=%d ra=%d %-12s ev=%d d=%6.0f ve=%4.1f lanes=%d rec=%d%s ego=%d/%d abs=%s/%s old=%s vis=%s | sig=%d %-5s %-20s tgt=%-2d | blink=%d/%d lat=%d lcs=%s | ovt=%s | road=%s spd=%s edge=%s est=%s off=%s geo=%s alc=%s gps=%s | %s blk=%s lamp=%s/%s | obs=%s fnav=%s yaw=%s hdg=%s rte=%s dr=%s side=%s ll=%s v3=%s\n' % (
          _t.monotonic(), _key[0], _key[1], _key[2], _key[3], _key[4], _key[5], _key[6],
          _key[7], _key[8], _recset, _key[9], _key[10],
          '-' if _abs is None else _abs, _abs_src, _old, _vis,
          _key[11], _key[12], _key[13], _key[14], _key[15], _key[16], _key[17], _key[18],
          '%s/%s' % (_ovt.get('state', '-'), _ovt.get('reason', '-')),
          _road, _spd, _edge, _est, _off, _geo_txt, _alc_txt, _gps_txt,
          _flags, _blk, _lamp.get('reason', '-'), _lamp.get('framesBuilt', '-'),
          _obs_txt, _fnav, _yaw_txt, _hdg_txt, _rte_txt, _dr, _side, _ll_txt, _v3_txt))
  except Exception:
    pass
