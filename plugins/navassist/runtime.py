"""One complete pure navigation cycle; no camera, socket or vehicle actuation."""
from __future__ import annotations

from .branch import BranchMatcher
from .map_data import MapData
from .blocker import LaneChangeBlocker
from .intent import LaneIntentCoordinator, TurnSignalCoordinator, build_intent
from .navstate import build as build_nav_state
from .oem import OemLaneSignals
from .phone_lane import PhoneLaneEvidence, planning_index
from .lane_estimate import estimate as lane_estimate
from .lane_number_v3 import LaneNumberV3, V3Config   # LANE_V3
from .v3_adapter import frame_from_runtime           # LANE_V3
from .lane_fused import FusedLaneMatcher
from .rec_gate import is_current_road_layout
from .avoid_confirm import AvoidanceConfirm, is_night as night_now
from .navstate import road_kind as classify_road_kind
from .position import AbsolutePosition
from .overtake import OvertakeController
from .road_total import RoadTotalMemory

# 绝对车道号防抖：新值必须持续这么久才切换，避免在最右车道两个来源来回跳。
ABS_DEBOUNCE_NS = 500_000_000
ABS_STALE_NS = 1_500_000_000

# 绕过车端 ALC「可用性」判断：只用自己的传感器（车道线/盲区/实线/路沿）。
# 车端雷达盲区与 DesireHelper 的盲区检查仍然生效。
BYPASS_OEM_CROSSING = True
# PLAN_LANES_HOLD 11-14：高德 API 版的车道引导只在路口前短暂下发（日志里大部分时间 lanes=0），
# 变道后几秒车道信息就消失，规划没有推荐车道，司机变回原车道后不会再提示。
# 只给规划（build_intent）沿用同一机动最近一次的车道列表，最多 30 秒、距离必须连续递减；
# 车道号融合/v3/邻道判断仍用原始 nav。设 0 关闭。
PLAN_LANES_HOLD_S = 30.0
from .topology import from_model
from .recording_observer import observe as observe_recording



def _resolve_road_kind(current):
  kind, name = "unknown", ""
  if current is None:
    return kind, name
  try:
    inner = current.snapshot
    kind = classify_road_kind(
      getattr(inner, "road_class", None), getattr(inner, "road_type", None),
      road_name=getattr(inner, "current_road", "") or "",
      speed_kph=float(getattr(inner, "speed_kph", 0.0) or 0.0),
      parallel_status=str(getattr(inner, "parallel_road_status", "unknown")),
      elevated_status=str(getattr(inner, "elevated_road_status", "unknown")))
    name = str(getattr(inner, "current_road", "") or "")
  except Exception:
    kind, name = "unknown", ""
  return kind, name


class NavigationRuntime:
  def __init__(self, settings):
    self.settings = settings
    self.branch = BranchMatcher()
    self.oem = OemLaneSignals()
    self.blocker = LaneChangeBlocker()
    self.position = AbsolutePosition()
    self.phone_lane = PhoneLaneEvidence()
    self.turns = TurnSignalCoordinator()
    self.lanes = LaneIntentCoordinator(max_changes=settings.max_lane_changes)
    self._topo_hold = None      # 模型拓扑短时抖动时的保持缓存
    self._abs_hold = None       # 绝对车道号的防抖状态
    self._lane_history = None   # 统一估计器用的历史值
    self._geo_lane = FusedLaneMatcher()       # 融合方案（主线，不再用 DeepSeek 几何匹配）
    self._lane_v3 = LaneNumberV3(V3Config())  # LANE_V3：车道号仲裁（只管手机显示和日志）
    self._lane_v3_mode = 'strict'             # 'strict'=拿不准报未知；'hold'=保持旧号；'off'=关闭
    self._road_total = None     # 道路实际车道总数（远离路口时稳定值）
    self._road_memory = RoadTotalMemory()
    self._avoid_confirm = AvoidanceConfirm()  # 避让打灯：夜里 2 帧、白天 3 帧
    self.overtake = OvertakeController()
    self.last_overtake = {}

  def _plan_lanes(self, nav, now_ns):
    """PLAN_LANES_HOLD：只用于规划输入的车道列表保持。"""
    try:
      if PLAN_LANES_HOLD_S <= 0:
        return nav
      key = (str(nav.get('sessionId', '')), str(nav.get('maneuver') or 'none'))
      d = float(nav.get('distanceM') or 0.0)
      lanes = list(nav.get('lanes') or ())
      if key[1] in ('none', 'unknown', 'destination', ''):
        self._lanes_hold = None
        return nav
      if lanes:
        self._lanes_hold = (key, lanes, nav.get('laneTotalCount', -1), d, now_ns, int(nav.get('maneuverEventId') or 0))
        return nav
      h = getattr(self, '_lanes_hold', None)
      if (h is not None and h[0] == key and 0 <= now_ns - h[4] <= PLAN_LANES_HOLD_S * 1e9
          and 0.0 < d <= h[3] + 20.0
          and not (int(nav.get('maneuverEventId') or 0) and h[5] and int(nav.get('maneuverEventId') or 0) != h[5])):
        return dict(nav, lanes=h[1], laneTotalCount=h[2], lanesHeld=True)
    except Exception:
      pass
    return nav

  def status_snapshot(self) -> dict:
    """只读状态：给手机 App 展示当前超车/视觉判定。"""
    ovt = dict(getattr(self, 'last_overtake', {}) or {})
    return {
      'overtake': {k: ovt.get(k) for k in ('state', 'reason', 'direction', 'count') if k in ovt},
      'settings': {
        'mode': int(getattr(self.settings, 'overtake_mode', 0)),
        'style': int(getattr(self.settings, 'overtake_style', 0)),
        'minKph': int(getattr(self.settings, 'overtake_min_kph', 0)),
        'diffKph': int(getattr(self.settings, 'overtake_diff_kph', 0)),
      },
    }

  def tick(self, current, model, model_ns, car, cc, now_ns, *, can_list=(), vehicle_fresh=False,
           left_phone=False, right_phone=False, turn_geometry_active=False,
           localization_valid=True, map_snapshot=None, phone_lane_observation=None,
           phone_lane_estimate=None, lane_offset_m=None, lane_width_m=None,
           lane_sigma_m=None, yaw_rate_dps=None, bearing_deg=None, route_bearing=None):
    self.oem.update(can_list, now_ns)
    oem = self.oem.payload(now_ns)
    topology = from_model(model, now_ns, model_ns)
    # 模型偶尔一帧看不到车道线时，不要立刻把本车位置清零：
    # 1.5 秒内沿用上一次有效拓扑，避免推荐车道/并道跟着抖。
    if not topology.get('valid'):
      held = getattr(self, '_topo_hold', None)
      if held is not None and now_ns - held[0] <= 1_500_000_000:
        topology = dict(held[1])
        topology['stale'] = True
      else:
        self._topo_hold = None
    else:
      self._topo_hold = (now_ns, dict(topology))
    nav = build_nav_state(current, now_ns, oem_nav_route_active=oem['navRouteActive'])
    # Read-only shadow diagnostics.  Deliberately not used by any downstream
    # planning, intent, lamp or lane-change input.
    _recording = observe_recording(nav, getattr(self, '_recording_road_key', None))
    if _recording.get('roadKey') is not None:
      self._recording_road_key = _recording['roadKey']
    topology['holdRoadRecording'] = _recording
    # The C3 lane model often cannot see lanes on ordinary roads; the phone's MNN estimate is the
    # driver-visible truth there, so use it as the lane geometry when it is fresh.
    est = phone_lane_estimate or {}
    if not topology.get('valid') or int(topology.get('visibleLaneCount', 0) or 0) <= 0:
      try:
        count, number, age = int(est.get('laneCount')), int(est.get('laneNumber')), int(est.get('ageNs', 1 << 62))
      except (TypeError, ValueError):
        count = number = 0; age = 1 << 62
      if est.get('valid') and count >= 1 and 1 <= number <= count and age < 1_000_000_000:
        topology.update(valid=True, visibleLaneCount=count, egoLaneIndexFromLeft=number - 1,
                        leftNeighborExists=number > 1, rightNeighborExists=number < count,
                        source='phoneLane')
        topology['phoneLaneCount'] = count
        if len(nav.get('lanes') or ()) == count:
          # The phone counts the whole road like AMap does: its lane number is an absolute index,
          # which is what lets a middle-lane recommendation be followed.
          topology['absoluteEgoIndex'] = number - 1
    nav['valid'] = bool(nav['valid'] and localization_valid)
    if not localization_valid and nav['reason'] == 'none':
      nav['reason'] = 'localLocalization'
    evidence = map_snapshot or MapData().snapshot(now_ns)
    # Broker TTL cannot extend the original CAN timestamp.
    if not 0 < evidence.get('stampNs', 0) <= now_ns or now_ns-evidence.get('stampNs', 0) > 1_000_000_000:
      evidence = MapData().snapshot(now_ns)
    if not self.settings.enabled:
      self.branch = BranchMatcher()
      evidence = MapData().snapshot(now_ns)
    nav['branchEvidence'] = self.branch.update(nav, evidence, now_ns)
    position = self.position.update(topology, nav, now_ns)
    candidate = self.phone_lane.update(phone_lane_observation, nav, now_ns,
      enabled=self.settings.enabled and self.settings.phone_lane_enabled)
    nav['phoneLaneEvidence'] = candidate
    # 用手机车道号推断邻道是否存在：模型看不到邻道时，避免协调器一直卡在
    # 「邻道观测未知 → 暂停」。只填补 None，不覆盖模型给出的判断。
    try:
      _ev = candidate or {}
      _n, _c = _ev.get('laneNumber'), _ev.get('laneCount')
      if _ev.get('valid') and type(_n) is int and type(_c) is int and 1 <= _n <= _c:
        if topology.get('leftNeighborExists') is None:
          topology['leftNeighborExists'] = _n > 1          # neighbor_from_phone
        if topology.get('rightNeighborExists') is None:
          topology['rightNeighborExists'] = _n < _c        # neighbor_from_phone
    except Exception:
      pass
    topology['estimatedEgoIndex'] = planning_index(candidate, nav,
      enabled=self.settings.enabled and self.settings.phone_lane_enabled)
    topology['phoneLanePlanningEnabled'] = self.settings.enabled and self.settings.phone_lane_enabled
    # PREFER_POSITION_OVER_PHONE：相机+地图锚定的绝对号（position.py）比手机 MNN 可靠。
    # 实测（4 车道、两者都可用 651 行）：手机比 position 小 1 的占 26%（171 行），
    # 也就是 MNN 常漏掉左侧一条车道。所以 position 有效时优先用它，手机退居兜底。
    _phone_abs = topology.get('absoluteEgoIndex')
    _phone_ok = isinstance(_phone_abs, int) and _phone_abs >= 0
    _pos_abs = (int(position['lane_index']) - 1) if position.get('valid') and position.get('lane_index') else None
    if _pos_abs is not None and _pos_abs >= 0:
      topology['absoluteEgoIndex'] = _pos_abs
      if _phone_ok and int(topology.get('visibleLaneCount', 0) or 0) == int(topology.get('phoneLaneCount', 0) or -1):
        topology['egoLaneIndexFromLeft'] = _phone_abs
    elif _phone_ok:
      topology['absoluteEgoIndex'] = _phone_abs
      if int(topology.get('visibleLaneCount', 0) or 0) == int(topology.get('phoneLaneCount', 0) or -1):
        topology['egoLaneIndexFromLeft'] = _phone_abs
    else:
      topology['absoluteEgoIndex'] = None
    try:
      from .phone import lane_line_state as _lls
      _line = _lls(now_ns=now_ns)
    except Exception:
      _line = {}
    try:
      topology['laneMarkingLeft'] = int(_line.get('left') or -1)
      topology['laneMarkingRight'] = int(_line.get('right') or -1)
    except Exception:
      pass
    # SOLID_LINE_LANE_NUMBER: 实线不再用来推断路沿/车道号（实线可能只是车道分隔线）。
    # 边缘推断：高德给整条路的车道数，手机只看得到可见范围。只认「真实路沿」
    # （模型拓扑里的 left/rightCarriagewayAnchored），不再用手机实线代替路沿。
    # EDGE_PLUS_SOLID：模型看到该侧路沿 + 手机判定该侧实线 → 本车就在最外侧车道。
    # 这比单看实线可靠（实线也可能只是车道分隔线），用来纠正「最左车道被数成第 2 条」。
    # SHADOW_OLD：把旧算法在同一份输入上再算一遍，只用于日志对比，不参与控制。
    _old_abs, _old_src = None, '-'
    try:
      _amap_o = len(nav.get('lanes') or ())
      _ev_o = candidate or {}
      _num_o, _cnt_o = int(_ev_o.get('laneNumber') or 0), int(_ev_o.get('laneCount') or 0)
      _vis_o = bool(_ev_o.get('valid')) and 1 <= _num_o <= max(_cnt_o, 1)
      _left_solid_o = int(_line.get('left') or 0) == 1
      _right_solid_o = int(_line.get('right') or 0) == 1
      if _vis_o and _amap_o >= 1 and _cnt_o == _amap_o:
        _old_abs, _old_src = _num_o - 1, 'phoneMatch'
      elif position.get('valid') and isinstance(position.get('lane_index'), int):
        _old_abs, _old_src = int(position['lane_index']) - 1, 'position'
      elif _vis_o and _amap_o >= 1:
        if _left_solid_o and _num_o == 1:
          _old_abs, _old_src = 0, 'oldEdge'
        elif _right_solid_o and _cnt_o >= 2 and _num_o == _cnt_o:
          _old_abs, _old_src = _amap_o - 1, 'oldEdge'
    except Exception:
      _old_abs, _old_src = None, '-'
    # LANE_PRIORITY_V2
    #   ① 左侧路沿（紧贴，或 路沿+实线）        → 第 1 条
    #   ② 右侧路沿紧贴可见最右 + 高德总数        → 高德总数 - 可见数 + (手机号 - 1)
    #   ③ 否则手机左侧计数                       → 手机号 - 1
    #   ④ 都没有                                  → 不猜
    if topology.get('absoluteEgoIndex') is None:
      try:
        _amap = len(nav.get('lanes') or ())
        _left_solid = int(_line.get('left') or 0) == 1
        _ev2 = candidate or {}
        _vis_number, _vis_count = int(_ev2.get('laneNumber') or 0), int(_ev2.get('laneCount') or 0)
        _has_vis = bool(_ev2.get('valid')) and 1 <= _vis_number <= max(_vis_count, 1)
        EDGE_GAP_LIMIT_M = 3.0
        E_DGE_GAP = EDGE_GAP_LIMIT_M
        _lg_raw = topology.get('leftEdgeGapM')
        _rg_raw = topology.get('rightEdgeGapM')
        _lgap = 99.0 if _lg_raw is None else float(_lg_raw)   # 0 米是合法紧贴，不能用 or
        _rgap = 99.0 if _rg_raw is None else float(_rg_raw)
        # EDGE_GAP_LIMIT_M：路沿必须在 3 米内才算「紧贴」，否则中间车道会被远处路沿带偏。
        _left_anchor = bool(topology.get('leftRoadEdge') or topology.get('leftCarriagewayAnchored')
                            or (topology.get('leftEdgeDetected') and _left_solid and _lgap <= E_DGE_GAP))
        # RIGHT_SOLID_ANCHOR：右侧路沿紧贴，或「检测到右路沿 + 右侧实线」都算右侧锚定。
        # 单独实线不采信（可能只是车道分隔线），必须有路沿配合。
        _right_solid = int(_line.get('right') or 0) == 1
        _right_anchor = bool(topology.get('rightCarriagewayAnchored')
                             or (topology.get('rightEdgeDetected') and _right_solid and _rgap <= E_DGE_GAP))
        if _left_anchor:
          # LEFT_ANCHOR_EGO：左侧路沿锚住窗口最左端 → 窗口第 1 条 = 高德第 1 条，
          # 所以绝对号 = 模型在窗口里的序号（中间车道不能一律写 0）。
          # 注意：ego=0（最左）会被 `or -1` 变成 -1，必须显式判断类型。
          _ego_raw = topology.get('egoLaneIndexFromLeft')
          _ego_i = int(_ego_raw) if isinstance(_ego_raw, int) and not isinstance(_ego_raw, bool) else -1
          if 0 <= _ego_i:
            _abs = _ego_i
          elif _has_vis:
            _abs = _vis_number - 1
          else:
            _abs = 0
          if _amap >= 1:
            _abs = max(0, min(_amap - 1, _abs))
          topology['absoluteEgoIndex'] = _abs
          topology['estimatedEgoIndex'] = _abs
          topology['absoluteSource'] = 'leftEdge'
        elif _right_anchor and _amap >= 1 and (not _has_vis or (_amap - _vis_count) <= 1):
          # ② 右侧路沿紧贴可见最右车道：可见最右 = 高德最后一条。
          # RIGHT_EDGE_TOTAL_GAP：只有「高德总数 - 可见数 ≤ 1」时才成立；
          # 差 2 条以上说明可见窗口没到路右端，反推会偏好几条（19:56 就是这种）。
          if _has_vis and _vis_count >= 1:
            _abs = _amap - _vis_count + (_vis_number - 1)
          else:
            _abs = _amap - 1
          topology['absoluteEgoIndex'] = max(0, min(_amap - 1, _abs))
          topology['estimatedEgoIndex'] = topology['absoluteEgoIndex']
          topology['absoluteSource'] = 'rightEdgeAmapTotal'
        elif _has_vis and _amap >= 1:
          # PHONE_ABS_NEEDS_AMAP：高德没给车道数时，手机窗口序号不是整条路的序号，
          # 直接当绝对号会系统性少算（最右车道被报成第 2 条）。宁可不报。
          _abs = min(_vis_number - 1, _amap - 1)
          topology['absoluteEgoIndex'] = max(0, _abs)
          topology['estimatedEgoIndex'] = topology['absoluteEgoIndex']
          topology['absoluteSource'] = 'phoneLeftCount'
      except Exception:
        pass
    # ABS_DEBUG/防抖：最右车道会在「右路沿反推」和「手机左侧计数」之间来回跳，
    # 要求新值连续稳定 500 毫秒才采纳，旧的继续用；超过 1.5 秒没有候选则清空。
    try:
      _cand = topology.get('absoluteEgoIndex')
      _h = self._abs_hold
      if not isinstance(_cand, int) or _cand < 0:
        if _h is not None and now_ns - _h['last'] > ABS_STALE_NS:
          self._abs_hold = None
          topology['absoluteEgoIndex'] = None
      else:
        if _h is None:
          self._abs_hold = dict(value=_cand, pending=None, since=now_ns, last=now_ns)
        elif _cand == _h['value']:
          _h['pending'] = None
          _h['last'] = now_ns
        else:
          if _h['pending'] != _cand:
            _h['pending'] = _cand
            _h['since'] = now_ns
          elif now_ns - _h['since'] >= ABS_DEBOUNCE_NS:
            _h['value'] = _cand
            _h['pending'] = None
            _h['last'] = now_ns
          _h['last'] = now_ns
        if _h is not None:
          topology['absoluteEgoIndex'] = _h['value']
          topology['estimatedEgoIndex'] = _h['value']
    except Exception:
      pass

    # 路种提前算好：融合接近窗口和 v3 锁号都要用（与规划门槛同一套）。
    _road_kind, _road_name = _resolve_road_kind(current)

    # Current-road count expires before fusion and display consume it.
    _map_lanes = list(nav.get('lanes') or ())
    _map_rec = tuple(l['index'] for l in _map_lanes if l.get('recommended') is True)
    _layout_allowed = is_current_road_layout(len(_map_lanes), _map_rec, self._road_total,
      nav.get('distanceM'), _road_kind, nav.get('maneuver'))
    self._road_total = self._road_memory.update(current, nav, now_ns,
      enabled=self.settings.enabled, layout_allowed=_layout_allowed)

    # FUSED_LANE：用融合方案接管车道号（航向积分 + GPS + 视觉 + 路口拓宽映射）。
    # 结果仍写在 geoValue 上，手机和后面的估计器逻辑不用改。置信度不够时退回估计器。
    try:
      _meta = model.meta if model is not None else None
      _geo = self._geo_lane.update(
        t=(now_ns / 1e9),
        nav=nav,
        topology=topology,
        candidate=candidate,
        road_total=self._road_total,
        lane_offset_m=lane_offset_m,
        lane_width_m=lane_width_m,
        lane_sigma_m=lane_sigma_m,
        speed_mps=float(getattr(car, 'vEgo', 0.0) or 0.0),
        yaw_rate_dps=yaw_rate_dps,
        bearing_deg=bearing_deg,
        route_bearing=route_bearing,
        lane_change_state=str(getattr(_meta, 'laneChangeState', '')) if _meta is not None else '',
        lane_change_direction=str(getattr(_meta, 'laneChangeDirection', '')) if _meta is not None else '',
        left_line=_line.get('left') if isinstance(_line, dict) else None,
        right_line=_line.get('right') if isinstance(_line, dict) else None,
        road_kind=_road_kind)
      topology['geoValue'] = _geo.get('value')
      topology['geoConfidence'] = _geo.get('confidence')
      topology['geoReason'] = _geo.get('reason')
      topology['geoOffsetM'] = _geo.get('offsetM')
      topology['fnav'] = _geo.get('debug') or {}
      if isinstance(_geo.get('value'), int) and _geo.get('confidence', 0.0) >= 0.5:
        topology['absoluteEgoIndex'] = int(_geo['value'])
        topology['estimatedEgoIndex'] = int(_geo['value'])
        topology['absoluteSource'] = str(_geo.get('reason'))
        self._lane_history = dict(value=int(_geo['value']), ns=now_ns)
    except Exception:
      topology['fnav'] = {'err': 'runtime'}

    # LANE_ESTIMATE_OBSERVE：统一估计器先只做观察，日志里和现有 abs 并排输出，
    # 跑够数据确认置信度表后再切换为正式输出。
    try:
      _est = lane_estimate(nav, topology, position, candidate, _line, self._lane_history, now_ns,
                           road_total=self._road_total)
      topology['estimateValue'] = _est.get('value')
      topology['estimateSource'] = _est.get('source')
      topology['estimateConfidence'] = _est.get('confidence')
      topology['estimateNote'] = _est.get('note')
      # GEO 优先：几何匹配有结论时它就是正式车道号，估计器只记日志不覆盖。
      _geo_wins = (isinstance(topology.get('geoValue'), int)
                   and float(topology.get('geoConfidence') or 0.0) >= 0.5)
      if isinstance(_est.get('value'), int) and not _geo_wins:
        topology['absoluteEgoIndex'] = int(_est['value'])
        topology['estimatedEgoIndex'] = int(_est['value'])
        topology['absoluteSource'] = 'est:' + str(_est.get('source'))
        if _est.get('confidence', 0.0) >= 0.6:
          self._lane_history = dict(value=int(_est['value']), ns=now_ns)
    except Exception:
      pass

    # LANE_V3：车道号仲裁。只写 topology['laneV3']（手机显示 + 日志），
    # 不改 absoluteEgoIndex/estimatedEgoIndex：规划、并道避让、超车、阻塞判断仍用原来的输入。
    if self._lane_v3_mode != 'off':
      try:
        _v3 = self._lane_v3.update(frame_from_runtime(
          now_ns=now_ns, nav=nav, topology=topology, candidate=candidate, road_total=self._road_total,
          geo=locals().get('_geo'), lane_offset_m=lane_offset_m, lane_width_m=lane_width_m,
          lane_sigma_m=lane_sigma_m, speed_mps=float(getattr(car, 'vEgo', 0.0) or 0.0),
          meta=getattr(model, 'meta', None) if model is not None else None, car=car,
          road_kind=_road_kind))
        _v3_val = _v3['strict'] if self._lane_v3_mode == 'strict' else _v3['hold']
        topology['laneV3'] = dict(_v3, value=_v3_val, amap_rec=list(_v3['amap_rec']))
        if self._road_total is None or not nav.get('lanes'):
          topology['laneV3'].update(provisional=True, reason='roadLayoutPending',
                                    road_layout_unknown=self._road_total is None)
          if self._road_total is None:
            topology['laneV3'].update(n=None, reason='roadLayoutUnknown')
      except Exception as _v3_exc:
        topology['laneV3'] = {'err': type(_v3_exc).__name__}

    # NEIGHBOR_FROM_ABS：模型只看得见 2-3 条车道，窗口外的邻道会被判成「不存在」，
    # 导致协调器一直 lanePositionRecoveryWaiting。绝对号 + 高德总数能确定邻道是否存在。
    try:
      _abs_n = topology.get('absoluteEgoIndex')
      _amap_n = len(nav.get('lanes') or ())
      if isinstance(_abs_n, int) and 0 <= _abs_n and _amap_n >= 1:
        topology['leftNeighborExists'] = bool(_abs_n > 0)
        topology['rightNeighborExists'] = bool(_abs_n < _amap_n - 1)
    except Exception:
      pass
    left_blocked, right_blocked, reasons = self.blocker.update(oem, topology,
      phone_left=left_phone, phone_right=right_phone,
      car_left=bool(getattr(car, 'leftBlindspot', False)),
      car_right=bool(getattr(car, 'rightBlindspot', False)),
      paint_left=_line.get('left') == 1 if _line else False,
      paint_right=_line.get('right') == 1 if _line else False,
      # 路口前的转弯/靠边：跨过实线是正常操作，实线不再拦截
      ignore_paint=bool(str(nav.get('maneuver', '')).startswith(('turn_', 'slight_', 'keep_'))
                        and 0.0 <= float(nav.get('maneuverDistanceM') or 0.0) <= 150.0))
    oem.update(leftBlocked=left_blocked, rightBlocked=right_blocked, blockReasons=list(reasons))
    for side in ('left', 'right'):
      if BYPASS_OEM_CROSSING:
        # 只信自己的观测：车端 ALC 不可用/过期不再否决，但自己的阻塞仍然生效。
        topology[side+'CrossingAllowed'] = not oem[side+'Blocked']
      else:
        topology[side+'CrossingAllowed'] = oem[side+'CrossingAllowed'] and not oem[side+'Blocked']
    usable_nav = dict(nav, valid=bool(nav['valid'] and vehicle_fresh),
                      linked=bool(nav.get('linked', nav['valid']) and vehicle_fresh),
                      routeActive=bool(nav.get('routeActive') and vehicle_fresh and self.settings.enabled))
    if not self.settings.enabled:
      usable_nav.update(valid=False, linked=False)
      self.turns.reset()
      self.lanes.reset()
      self._avoid_confirm.reset()
    meta = getattr(model, 'meta', None)
    # _road_kind / _road_name 已在融合前算过，这里沿用。
    overtake = self.overtake.update(car=car, model=model, topology=topology, nav=usable_nav,
      now_ns=now_ns, settings=self.settings, road_kind=_road_kind,
      left_blocked=left_blocked, right_blocked=right_blocked,
      blindspot_left=bool(getattr(car, 'leftBlindspot', False)),
      blindspot_right=bool(getattr(car, 'rightBlindspot', False)),
      lateral_active=bool(vehicle_fresh and getattr(cc, 'latActive', False)),
      lane_change_state=str(getattr(meta, 'laneChangeState', 'off')))
    usable_nav['overtake'] = overtake
    self.last_overtake = overtake
    nav['overtake'] = overtake
    intent = build_intent(self._plan_lanes(usable_nav, now_ns), topology, settings=self.settings,
      v_ego=float(getattr(car, 'vEgo', 0.)), now_ns=now_ns, left_blocked=left_blocked, right_blocked=right_blocked,
      avoid_confirm=self._avoid_confirm, is_night=night_now(),
      blindspot_left=bool(getattr(car, 'leftBlindspot', False)),
      blindspot_right=bool(getattr(car, 'rightBlindspot', False)),
      lateral_active=bool(vehicle_fresh and getattr(cc, 'latActive', False)),
      left_blinker=bool(getattr(car, 'leftBlinker', False)), right_blinker=bool(getattr(car, 'rightBlinker', False)),
      brake_pressed=bool(getattr(car, 'brakePressed', False)), gas_pressed=bool(getattr(car, 'gasPressed', False)),
      steering_pressed=bool(getattr(car, 'steeringPressed', False)),
      model_state=str(getattr(meta, 'laneChangeState', 'off')),
      model_direction=str(getattr(meta, 'laneChangeDirection', 'none')), turn_geometry_active=turn_geometry_active,
      turns=self.turns, lanes=self.lanes, overtake=overtake)
    return dict(nav=nav, topology=topology, intent=intent, oem=oem, position=position,
                road_kind=_road_kind, road_name=_road_name,
                old_abs=_old_abs, old_src=_old_src)
