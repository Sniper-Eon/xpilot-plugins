"""One complete pure navigation cycle; no camera, socket or vehicle actuation."""
from __future__ import annotations

from .branch import BranchMatcher
from .map_data import MapData
from .blocker import LaneChangeBlocker
from .intent import LaneIntentCoordinator, TurnSignalCoordinator, build_intent
from .navstate import build as build_nav_state
from .oem import OemLaneSignals
from .phone_lane import PhoneLaneEvidence, planning_index
from .position import AbsolutePosition
from .overtake import OvertakeController

# 绕过车端 ALC「可用性」判断：只用自己的传感器（车道线/盲区/实线/路沿）。
# 车端雷达盲区与 DesireHelper 的盲区检查仍然生效。
BYPASS_OEM_CROSSING = True
from .topology import from_model


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
    self.overtake = OvertakeController()
    self.last_overtake = {}

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
           phone_lane_estimate=None):
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
    # 手机 MNN 是车道编号的第一决策源：它报出车道号时直接采信，模型只做补充。
    _phone_abs = topology.get('absoluteEgoIndex')
    _phone_ok = isinstance(_phone_abs, int) and _phone_abs >= 0
    if _phone_ok:
      topology['absoluteEgoIndex'] = _phone_abs
      if int(topology.get('visibleLaneCount', 0) or 0) == int(topology.get('phoneLaneCount', 0) or -1):
        topology['egoLaneIndexFromLeft'] = _phone_abs
    else:
      topology['absoluteEgoIndex'] = position['lane_index']-1 if position['valid'] else None
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
    # 手机虚实线补充锚定：模型看不到路沿、但手机判定该侧是实线且本车在最外侧车道时，
    # 把这一侧视为车道计数基准（用于绝对车位和推荐车道换算）。
    try:
      _ego_now = int(topology.get('egoLaneIndexFromLeft', -1) or -1)
      _cnt_now = int(topology.get('visibleLaneCount', 0) or 0)
      if _ego_now == 0 and int(_line.get('left') or 0) == 1:
        topology['leftCarriagewayAnchored'] = True
        topology['phoneLineAnchor'] = 'left'
      if _cnt_now >= 2 and _ego_now == _cnt_now - 1 and int(_line.get('right') or 0) == 1:
        topology['rightCarriagewayAnchored'] = True
        topology['phoneLineAnchor'] = 'right'
    except Exception:
      pass
    # 边缘推断：高德给整条路的车道数，手机只看得到可见范围。当两边数量不一致时，
    # 用实线边界判断本车是否贴在某侧路沿：贴左侧路沿且在最左可见车道 → 绝对第 1 条；
    # 贴右侧路沿且在最右可见车道 → 绝对最后一条。仅在缺少绝对号时使用。
    if topology.get('absoluteEgoIndex') is None:
      try:
        _amap = len(nav.get('lanes') or ())
        _ev = candidate or {}
        _number, _count = int(_ev.get('laneNumber') or 0), int(_ev.get('laneCount') or 0)
        if _amap >= 1 and _ev.get('valid') and _number >= 1 and 1 <= _count <= _amap:
          _visual = _number - 1
          _abs = None
          if int(_line.get('left') or 0) == 1 and _visual == 0:
            _abs = 0
          elif int(_line.get('right') or 0) == 1 and _count >= 2 and _visual == _count - 1:
            _abs = _amap - 1
          if _abs is not None:
            topology['absoluteEgoIndex'] = _abs
            topology['estimatedEgoIndex'] = _abs
            topology['absoluteSource'] = 'edgeInference'
      except Exception:
        pass
    left_blocked, right_blocked, reasons = self.blocker.update(oem, topology,
      phone_left=left_phone, phone_right=right_phone,
      car_left=bool(getattr(car, 'leftBlindspot', False)),
      car_right=bool(getattr(car, 'rightBlindspot', False)),
      paint_left=_line.get('left') == 1 if _line else False,
      paint_right=_line.get('right') == 1 if _line else False)
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
    meta = getattr(model, 'meta', None)
    _snap = current
    _road_kind = 'unknown'
    if _snap is not None:
      try:
        from .navstate import road_kind as _rk
        _inner = _snap.snapshot
        _road_kind = _rk(getattr(_inner, 'road_class', None), getattr(_inner, 'road_type', None),
                         road_name=getattr(_inner, 'current_road', '') or '',
                         speed_kph=float(getattr(_inner, 'speed_kph', 0.0) or 0.0),
                         parallel_status=str(getattr(_inner, 'parallel_road_status', 'unknown')),
                         elevated_status=str(getattr(_inner, 'elevated_road_status', 'unknown')))
      except Exception:
        _road_kind = 'unknown'
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
    intent = build_intent(usable_nav, topology, settings=self.settings,
      v_ego=float(getattr(car, 'vEgo', 0.)), now_ns=now_ns, left_blocked=left_blocked, right_blocked=right_blocked,
      blindspot_left=bool(getattr(car, 'leftBlindspot', False)),
      blindspot_right=bool(getattr(car, 'rightBlindspot', False)),
      lateral_active=bool(vehicle_fresh and getattr(cc, 'latActive', False)),
      left_blinker=bool(getattr(car, 'leftBlinker', False)), right_blinker=bool(getattr(car, 'rightBlinker', False)),
      brake_pressed=bool(getattr(car, 'brakePressed', False)), gas_pressed=bool(getattr(car, 'gasPressed', False)),
      steering_pressed=bool(getattr(car, 'steeringPressed', False)),
      model_state=str(getattr(meta, 'laneChangeState', 'off')),
      model_direction=str(getattr(meta, 'laneChangeDirection', 'none')), turn_geometry_active=turn_geometry_active,
      turns=self.turns, lanes=self.lanes, overtake=overtake)
    return dict(nav=nav, topology=topology, intent=intent, oem=oem, position=position)
