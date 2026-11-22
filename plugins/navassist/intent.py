"""Adapt plugin messages to the verified legacy preparation state machines.

Fresh absolute evidence or explicitly enabled, count-matched phone estimates
translate map indices. Same-direction edge fallback
remains separate evidence and inherits the bounded source-continuity checks.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace as N

from .coordinator import NavLaneIntentCoordinator, NavTurnSignalCoordinator
from .intent_types import LaneIntentDirection, LaneTopologyInput, LaneVehicleInput, NavLanePlan, NavTurnPlan, ObservedLaneChangeState
from .planning import build_lane_plan, lane_alignment_may_start, RELATIVE_ROUTE_MANEUVERS

# JUNCTION_NO_LC：路口/红绿灯前 50 米内不发起任何新的变道（推荐车道变道、超车/避让、并道类转弯提示灯）。
# 距离来源：高德引导的 distanceM（到下一个机动点/路口的距离，日志字段 d=）。高德 API 版没有红绿灯距离字段。
# 只拦“发起”，已经开始的变道不打断。
JUNCTION_NO_LC_M = 50.0
# 并道类提示灯：车端看到灯就会自己变道，所以在 50 米内同样算“发起变道”。真正的路口转弯灯（turn*/sharp*/uTurn*）不拦。
_LC_TYPE_LAMPS = frozenset(("slightLeft", "slightRight", "keepLeft", "keepRight",
                            "exitLeft", "exitRight", "rampLeft", "rampRight", "mergeLeft", "mergeRight"))
# 轻微左/右与保持左/右本质是「进入分流/专用道」的路线引导。需要换道时由
# LaneIntentCoordinator 负责唯一的一次提示；已经在推荐专用道后，不能再由
# NavTurnSignalCoordinator 以同方向补一次“路口灯”，否则车端会重新进入转向意图，
# 使通过分流口后的速度被压住。真正 turn*/sharp*/uTurn* 路口转弯不在此集合。
_DEDICATED_LANE_GUIDANCE = frozenset(("slightLeft", "slightRight", "keepLeft", "keepRight"))


def junction_distance_m(nav):
  """到下一个路口/机动点的距离（米）。没有导航或距离未知时返回 None。"""
  man = str(nav.get('maneuver') or 'none')
  try:
    d = float(nav.get('distanceM') or 0.0)
  except (TypeError, ValueError):
    d = 0.0
  if man not in ('', 'none', 'unknown', 'destination'):
    # 高德在到达机动点时报 0：按“就在路口”处理。
    return max(0.0, d)
  # 路口换段时当前机动常报 none，用下一个机动的距离兜底。
  nxt = str(nav.get('nextManeuver') or 'none')
  try:
    nd = float(nav.get('nextDistanceM') or 0.0)
  except (TypeError, ValueError):
    nd = 0.0
  if nxt not in ('', 'none', 'unknown', 'destination') and nd > 0.0:
    return nd
  return None


def junction_no_lane_change(nav):
  d = junction_distance_m(nav)
  return bool(d is not None and d <= JUNCTION_NO_LC_M and (nav.get('routeActive') or nav.get('valid')))


def camel(name):
  first, *rest = str(name).split('_')
  return first+''.join(p[:1].upper()+p[1:] for p in rest)


def navigation(nav):
  items = nav.get('lanes') or []
  count = nav.get('laneTotalCount', -1)
  if type(count) is not int or not 1 <= count <= 16:
    count = max((int(l.get('index', -1))+1 for l in items), default=0)
  if not items:
    count = 0
  by_index = {int(l['index']): l for l in items if type(l.get('index')) is int}
  return N(valid=bool(nav.get('valid')), stale=bool(nav.get('stale', False)),
           sessionId=str(nav.get('sessionId', '')), routeRevision=int(nav.get('routeRevision', 0)),
           maneuverEventId=int(nav.get('maneuverEventId', 0)), maneuver=camel(nav.get('maneuver', 'none')),
           maneuverDistanceM=float(nav.get('distanceM', 0)),
           lanes=[N(index=i, recommended=by_index.get(i, {}).get('recommended') is True) for i in range(count)])


@dataclass
class LanePlan:
  direction: str = 'none'
  target_lane: int = -1
  absolute_target: int = -1
  reason: str = 'idle'
  edge_anchored: bool = False
  core: object = None
  topology: object = None
  speed: float = 0.


def planning_ego_index(topology):
  # Model ownership clears stale geometry fallback when its observation is unknown.
  absolute = topology.get('absoluteEgoIndex')
  if isinstance(absolute, int) and absolute >= 0:
    return absolute
  if topology.get('phoneLanePlanningEnabled'):
    estimated = topology.get('estimatedEgoIndex')
    if isinstance(estimated, int):
      return estimated
  return None


def lane_plan(nav, topology, settings, *, v_ego, avoid_confirm=None, is_night=False):
  n = navigation(nav)
  count, ego = int(topology.get('visibleLaneCount', 0)), int(topology.get('egoLaneIndexFromLeft', -1))
  absolute = planning_ego_index(topology)
  if type(absolute) is not int:
    absolute = None
  core = build_lane_plan(n, N(visibleLaneCount=count, egoLaneIndexFromLeft=ego),
                         healthy=True, settings=settings, amap_ego_index=absolute,
                         avoid_confirm=avoid_confirm, is_night=is_night)
  if core.valid and getattr(core, 'absolute_ego_index', None) is not None:
    ego = int(core.absolute_ego_index)  # ABS_STEP：绝对车道计划按绝对号算方向
  target = NavLaneIntentCoordinator._target(core, ego) if core.valid else None
  direction = (NavLaneIntentCoordinator._relative_direction(core) or
               NavLaneIntentCoordinator._direction(ego, target)) if target is not None else LaneIntentDirection.none
  # The facade's target is adjacent; the core retains the actual route target.
  adjacent = NavLaneIntentCoordinator._adjacent_target_index(ego, direction) if direction else -1
  return LanePlan('left' if direction == LaneIntentDirection.left else 'right' if direction else 'none',
                  adjacent, -1, 'edgeFallback' if core.heuristic else 'modelLane' if topology.get('phoneLanePlanningEnabled') else 'absoluteLane', absolute is not None,
                  core, topology, v_ego)


def payload(intent, nav):
  return dict(valid=bool(nav.get('linked', nav.get('valid'))), sessionId=str(nav.get('sessionId', '')),
              routeRevision=int(nav.get('routeRevision', 0)), maneuverEventId=int(nav.get('maneuverEventId', 0)),
              signalRequested=intent.signal_requested, direction=intent.direction.name,
              targetLaneIndex=intent.target_lane_index, spLaneChangeReady=intent.lane_change_ready,
              laneChangeAllowed=intent.lane_change_ready, reason=intent.reason, requestId=intent.request_id,
              forkNow=False, allowUnknownCrossing=False, ignoreSolidBoundary=False,
              signalPurpose='nativeLaneChange' if camel(nav.get('maneuver', 'none')) in ('slightLeft', 'slightRight')
                and intent.target_lane_index < 0 else 'lanePreparation' if nav.get('maneuver') in
                ('merge_left', 'merge_right', 'exit_left', 'exit_right', 'ramp_left', 'ramp_right')
                or intent.target_lane_index >= 0 else 'junction')


class TurnSignalCoordinator:
  def __init__(self):
    self.core = NavTurnSignalCoordinator()
    self._synth_key = None
    self._synth_id = 0
    self._synth_last_distance = None
    self._yield_until_ns = 0
    self._lamp_seen_key = None
    self._lamp_off_since_ns = 0
    self._lamp_drops = 0
    self._real_event = None   # TURN_EV_STICKY：(session, maneuver, event_id, distance, now_ns)
    self._lc_lamp_key = None  # JUNCTION_NO_LC：已在 50 米外亮起的并道类提示灯（允许继续，不算新发起）

  def reset(self):
    self.core = NavTurnSignalCoordinator()
    self._yield_until_ns = 0
    self._lamp_seen_key = None
    self._lamp_off_since_ns = 0
    self._lamp_drops = 0

  def update(self, nav, *, speed_mps, now_ns, lookahead_time_s=8., lookahead_distance_m=None,
             turn_geometry_active=False, left_blinker=False, right_blinker=False):
    n = navigation(nav)
    # Route-active but not yet position-matched still carries guidance: arm the lamp early, while lane
    # change readiness remains gated by the fully valid/matched nav state.
    armed = bool((nav.get('linked', nav.get('valid', False)) or nav.get('routeActive', False))
                 and not nav.get('stale', False))
    event_id = int(n.maneuverEventId)
    # TURN_EV_STICKY：高德 API 版同一个路口的事件号会在真实号和 0 之间来回跳（日志 21:18:37–21:19:12 右转，
    # 3585↔0 跳了 4 次，每次都被当成新提示重新打灯）。同一路线、同一机动、距离连续时沿用上一个真实事件号。
    if event_id:
      self._real_event = (n.sessionId, n.maneuver, event_id, n.maneuverDistanceM, now_ns)
    elif self._real_event is not None:
      _s, _m, _e, _d, _t = self._real_event
      if (_s == n.sessionId and _m == n.maneuver and now_ns - _t <= 30_000_000_000
          and abs(n.maneuverDistanceM - _d) <= 60.0):
        event_id = _e
        n = type(n)(**{**n.__dict__, 'maneuverEventId': _e})
    # 路口换段时手机常把当前机动报成 none（ev=0），此时用下一步机动兜底，
    # 否则转弯那一刻灯反而不亮。
    if armed and n.maneuver in ("", "none", "unknown"):
      _next = camel(nav.get('nextManeuver', 'none'))
      try:
        _next_d = float(nav.get('nextDistanceM') or 0.0)
      except (TypeError, ValueError):
        _next_d = 0.0
      if _next not in ("", "none", "destination", "unknown") and 0.0 < _next_d <= 200.0:
        n = type(n)(**{**n.__dict__, 'maneuver': _next, 'maneuverDistanceM': _next_d})
    if event_id == 0 and armed and n.maneuver not in ("", "none", "destination", "unknown") and n.maneuverDistanceM > 0:
      # Keep one synthetic request through route refreshes. A maneuver/session
      # change or a near-to-far distance reset still starts a new intersection.
      key = (n.sessionId, n.maneuver)
      passed = (self._synth_last_distance is not None and self._synth_last_distance < 30.0
                and n.maneuverDistanceM > 100.0)
      if key != self._synth_key or passed:
        self._synth_key = key
        self._synth_id += 1
      event_id = self._synth_id
    if event_id:
      self._synth_last_distance = n.maneuverDistanceM
    plan = NavTurnPlan(armed, n.sessionId, n.routeRevision, event_id, n.maneuver, n.maneuverDistanceM)
    out = payload(self.core.update(plan, speed_mps=speed_mps, now_ns=now_ns,
                                  lookahead_time_s=lookahead_time_s,
                                  lookahead_distance_m=lookahead_distance_m,
                                  turn_geometry_active=turn_geometry_active), nav)
    key = (n.sessionId, n.routeRevision, n.maneuverEventId)
    ours = 'right' if out.get('direction') == 'RIGHT' else 'left' if out.get('direction') == 'LEFT' else ''
    opposing = bool(ours and ((ours == 'right' and left_blinker) or (ours == 'left' and right_blinker)))
    if opposing:
      # The driver used the stalk against navigation: hand the lamp over, then take the route back.
      self.core.reset()
      self._lamp_seen_key = None
      self._lamp_off_since_ns = 0
      self._lamp_drops = 0
      self._yield_until_ns = now_ns + 1_500_000_000
      return dict(out, signalRequested=False, direction='none', reason='driverYielding')
    if now_ns < self._yield_until_ns and (left_blinker or right_blinker):
      return dict(out, signalRequested=False, direction='none', reason='driverYielding')
    if not out['signalRequested']:
      self._lamp_seen_key = None
      self._lamp_off_since_ns = 0
      self._lamp_drops = 0
      return out
    lamp_on = (right_blinker if ours == 'right' else left_blinker) if ours else False
    if lamp_on:
      if self._lamp_seen_key == key and self._lamp_off_since_ns:
        self._lamp_drops += 1  # the car handed the lamp back while we still asked for it
      self._lamp_seen_key = key
      self._lamp_off_since_ns = 0
      if self._lamp_drops >= 2:
        self.core.reset()
        self._lamp_seen_key = None
        self._lamp_off_since_ns = 0
        self._lamp_drops = 0
        return dict(out, signalRequested=False, direction='none', reason='lampRejected')
    elif self._lamp_seen_key == key and not left_blinker and not right_blinker:
      if self._lamp_off_since_ns == 0:
        self._lamp_off_since_ns = now_ns
      elif now_ns - self._lamp_off_since_ns > 400_000_000:
        self.core.reset()
        self._lamp_seen_key = None
        self._lamp_off_since_ns = 0
        return dict(out, signalRequested=False, direction='none', reason='driverCancelled')
    return out


class LaneIntentCoordinator:
  def __init__(self, *, max_changes=5):
    self.max_changes = max_changes
    self.core = NavLaneIntentCoordinator(max_changes=max_changes)
    self._completed_relative_event = None
    self._owned_lane_event = None
    self._hold = None

  def reset(self):
    self.core = NavLaneIntentCoordinator(max_changes=self.max_changes)
    self._completed_relative_event = None
    self._owned_lane_event = None
    self._hold = None

  def update(self, nav, plan, *, now_ns, topology_valid, left_blocked, right_blocked,
             blindspot_left, blindspot_right, lateral_active, left_blinker=False, right_blinker=False,
             brake_pressed=False, gas_pressed=False, steering_pressed=False,
             model_state='off', model_direction='none', allow_new_lane_change=True):
    t = plan.topology or {}
    count, ego = int(t.get('visibleLaneCount', 0)), int(t.get('egoLaneIndexFromLeft', -1))

    def neighbor(side, present):
      if not topology_valid:
        return None
      return True if t.get(side+'NeighborExists', present) else False if t.get(side+'RoadEdge') else None

    topology = LaneTopologyInput(topology_valid, count, ego, neighbor('left', ego > 0),
      neighbor('right', 0 <= ego < count-1),
      bool(t.get('leftCrossingAllowed') or plan.core.allow_unknown_crossing) and not left_blocked and not t.get('leftRoadEdge'),
      bool(t.get('rightCrossingAllowed') or plan.core.allow_unknown_crossing) and not right_blocked and not t.get('rightRoadEdge'))
    state = {'off': ObservedLaneChangeState.off, 'preLaneChange': ObservedLaneChangeState.pre,
             'laneChangeStarting': ObservedLaneChangeState.starting,
             'laneChangeFinishing': ObservedLaneChangeState.finishing}.get(str(model_state), ObservedLaneChangeState.off)
    direction = {'none': LaneIntentDirection.none, 'left': LaneIntentDirection.left,
                 'right': LaneIntentDirection.right}.get(str(model_direction), LaneIntentDirection.none)
    vehicle = LaneVehicleInput(lateral_active, plan.speed, blindspot_left, blindspot_right,
      left_blinker, right_blinker, brake_pressed, gas_pressed, steering_pressed, state, direction)
    try:   # REPLAN_RESET：司机变回原车道后允许重新规划（只清“等绝对号”标记，不改变道执行条件）
      self.core.note_abs_observation(planning_ego_index(t), state == ObservedLaneChangeState.starting, now_ns)
    except Exception:
      pass
    result = self.core.update(plan.core, topology, vehicle, now_ns=now_ns,
                              allow_new_lane_change=allow_new_lane_change)
    event = (nav.get('sessionId'), nav.get('routeRevision'), nav.get('maneuverEventId'))
    if plan.core.relative_change_limit == 1 and result.reason == 'laneChangeObserved':
      self._completed_relative_event = event
    if result.signal_requested:
      self._owned_lane_event = event
    out = dict(payload(result, nav), relativeStepComplete=self._completed_relative_event == event,
               laneRequestOwned=self._owned_lane_event == event)
    # A started change must not be dropped by a one-frame plan gap: that makes the host re-press the
    # stalk and the lamp blinks. Hold the same request briefly instead.
    prepared = str(model_state) in ('preLaneChange', 'laneChangeStarting', 'laneChangeFinishing')
    if out['signalRequested'] and int(out.get('targetLaneIndex', -1)) >= 0:
      self._hold = (event, out, now_ns + 4_000_000_000)
    elif self._hold is not None:
      held_event, held_out, until_ns = self._hold
      if held_event == event and now_ns <= until_ns and prepared:
        return dict(held_out, reason='laneHold')
      self._hold = None
    return out


def _at_road_edge(direction, topology):
  """True when the requested side is the carriageway edge (no lane to move into)."""
  _dir = str(direction or 'none').lower()
  if _dir not in ('left', 'right'):
    return False
  # 注意：不能用 `int(x or 0)`，最左车道的 ego=0 会被 `or` 当成假值变成 -1。
  def _as_int(value, fallback):
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else fallback
  _count = _as_int(topology.get('visibleLaneCount'), 0)
  _ego = _as_int(topology.get('egoLaneIndexFromLeft'), -1)
  _abs_ego = topology.get('absoluteEgoIndex')
  _abs_known = isinstance(_abs_ego, int) and not isinstance(_abs_ego, bool) and _abs_ego >= 0
  if _abs_known and not (0 <= _ego < _count):
    _ego, _count = _abs_ego, max(_count, _abs_ego + 1)
  if _count > 1 and 0 <= _ego < _count:
    return (_dir == 'left' and _ego == 0) or (_dir == 'right' and _ego == _count - 1)
  # 只知道绝对号、不知道总数时，绝对号 0 就是最左车道。
  if _abs_known and _dir == 'left' and _abs_ego == 0:
    return True
  # 车道号未知时，手机判定的实线侧也视为路沿。
  if _dir == 'left':
    return int(topology.get('laneMarkingLeft', -1) or -1) == 1
  return int(topology.get('laneMarkingRight', -1) or -1) == 1


def build_intent(nav, topology, *, turns, **kw):
  """JUNCTION_NO_LC 外层：路口 50 米内不让并道类提示灯（无目标车道、车端会自己变道）新亮起。
  推荐车道变道 / 超车避让在 _build_intent_core 里通过 allow_new_lane_change 拦。"""
  out = _build_intent_core(nav, topology, turns=turns, **kw)
  try:
    if (out.get('signalRequested') and int(out.get('targetLaneIndex', -1)) < 0
        and camel(nav.get('maneuver', 'none')) in _LC_TYPE_LAMPS):
      _lk = (str(nav.get('sessionId', '')), int(out.get('requestId', 0) or 0), str(out.get('direction')))
      if getattr(turns, '_lc_lamp_key', None) == _lk:
        pass                      # 50 米外已经发出的同一个提示灯：继续，不算新发起
      elif junction_no_lane_change(nav):
        out = dict(out, signalRequested=False, spLaneChangeReady=False, laneChangeAllowed=False,
                   direction='none', reason='junctionNoLaneChange')
      else:
        turns._lc_lamp_key = _lk
  except Exception:
    pass
  return out


def _build_intent_core(nav, topology, *, settings, v_ego, now_ns, left_blocked, right_blocked,
                 blindspot_left, blindspot_right, lateral_active, turns, lanes,
                 left_blinker=False, right_blinker=False, brake_pressed=False, gas_pressed=False,
                 steering_pressed=False, model_state='off', model_direction='none', turn_geometry_active=False,
                 overtake=None, avoid_confirm=None, is_night=False):
  turn = turns.update(nav, speed_mps=v_ego, now_ns=now_ns, lookahead_time_s=settings.signal_lead_time_s,
                      lookahead_distance_m=settings.turn_lane_lookahead_m,
                      turn_geometry_active=turn_geometry_active,
                      left_blinker=left_blinker, right_blinker=right_blinker)
  n = navigation(nav)
  # JUNCTION_NO_LC：50 米内不发起新的变道。
  _jn = junction_no_lane_change(nav)
  intersection = n.maneuver in ('turnLeft', 'sharpLeft', 'uTurnLeft', 'turnRight', 'sharpRight', 'uTurnRight')
  approaching = bool(intersection and turn['signalRequested'])
  plan = lane_plan(nav, topology, settings, v_ego=v_ego,
                   avoid_confirm=avoid_confirm, is_night=is_night)
  _overtake_plan = False
  if overtake and overtake.get('request') and str(overtake.get('direction')) in ('left', 'right'):
    _count = int(topology.get('visibleLaneCount', 0) or 0)
    _ego = topology.get('egoLaneIndexFromLeft', -1)
    _ego = int(_ego) if isinstance(_ego, int) and not isinstance(_ego, bool) else -1  # 最左车道 ego=0 不能被 `or -1` 吃掉
    if _count > 1 and 0 <= _ego < _count:
      _target = max(0, _ego - 1) if overtake['direction'] == 'left' else min(_count - 1, _ego + 1)
      if _target != _ego:
        # OVT_WRAP：协调器要的是 LanePlan 包装（.core/.topology/.speed），不是裸 NavLanePlan。
        plan = LanePlan(str(overtake['direction']), _target, -1, 'overtake', False,
                        NavLanePlan(True, str(nav.get('sessionId', '')), int(nav.get('routeRevision', 0)),
                                    int(nav.get('maneuverEventId', 0) or 0), _count, (_target,), heuristic=True,
                                    allow_unknown_crossing=False, relative_change_limit=1),
                        topology, v_ego)
        _overtake_plan = True
  out = lanes.update(nav, plan, now_ns=now_ns, topology_valid=bool(topology.get('valid')),
    left_blocked=left_blocked, right_blocked=right_blocked,
    blindspot_left=blindspot_left, blindspot_right=blindspot_right, lateral_active=lateral_active,
    left_blinker=left_blinker, right_blinker=right_blinker, brake_pressed=brake_pressed,
    gas_pressed=gas_pressed, steering_pressed=steering_pressed, model_state=model_state,
    model_direction=model_direction,
    # 超车不依赖导航机动距离（无路线/d=0 时也可超车）；路口打灯窗口 approaching 仍然拦。
    allow_new_lane_change=(n.maneuverDistanceM > 0 or _overtake_plan) and not approaching and not _jn)
  if (n.maneuver in RELATIVE_ROUTE_MANEUVERS and planning_ego_index(topology) is None
      and out.get('relativeStepComplete')):
    out.update(signalRequested=False, spLaneChangeReady=False, laneChangeAllowed=False, reason='heuristicChangeLimit')
    return out
  if out['signalRequested']:
    # 并道灯也不能往路沿那一侧亮：已经在最左/最右车道时，再往那一侧并没有车道。
    # 只拦并道请求，路口转弯灯（turn*/sharp*/uTurn*）不受影响。
    # ABS_STEP：绝对车道计划的路沿由高德车道数和可见路沿标志判断（已在协调器里），不按可见窗口边缘拦。
    _abs_plan = getattr(plan.core, 'absolute_ego_index', None) is not None
    if not _abs_plan and _at_road_edge(out.get('direction'), topology):
      return dict(out, signalRequested=False, spLaneChangeReady=False, laneChangeAllowed=False,
                  reason='atRoadEdge')
    return out
  if settings.turn_signal_enabled and turn['signalRequested']:
    # 专用道/分流引导只能由车道协调器发灯。若已经进入专用道（或本来无需换道），
    # 不允许 turn-only fallback 再点同方向灯；避免在季华五路这类右前方专用道后
    # 又触发一次右灯。普通的左/右转、急转和掉头仍完整走原来的 turn fallback。
    if n.maneuver in _DEDICATED_LANE_GUIDANCE:
      return out
    # A physical edge proves there is no adjacent corridor on this side.
    # Apply this before the turn-only return, where the old edge check was
    # unreachable. A visible-window boundary alone is not a road edge.
    _side = str(turn.get('direction', '')).lower()
    if (n.maneuver in _LC_TYPE_LAMPS and _side in ('left', 'right')
        and topology.get(_side + 'RoadEdge') is True):
      return dict(out, reason='atRoadEdge')
    relative_route_action = n.maneuver in ('mergeLeft', 'mergeRight', 'exitLeft', 'exitRight', 'rampLeft', 'rampRight')
    if relative_route_action and out.get('laneRequestOwned'):
      return out  # Never bypass a lane coordinator's pause/abort via a turn-only fallback.
    if not intersection and out['reason'] in ('alreadyInRecommendedLane', 'noNeighbor'):
      return out
    # A completed relative merge cannot turn its lamp back on via the turn-only
    # fallback after the one-step lane coordinator has ended the request.
    if relative_route_action and out['reason'] in ('heuristicChangeLimit', 'changeLimit'):
      return out
    return turn
  if out['reason'] in ('routeChanged', 'neighborObservationPaused', 'crossingWaitTimeout') or out['reason'].startswith('lanePosition'):
    return out
  # 已经在要并过去那一侧的路沿：为「并道」点灯已经没有意义，直接不发（路口转弯灯不受影响）
  _LANE_CHANGE_LAMPS = frozenset(("slightLeft", "slightRight", "keepLeft", "keepRight",
                                  "exitLeft", "exitRight", "rampLeft", "rampRight", "mergeLeft", "mergeRight"))
  if (turn.get('signalRequested') and str(n.maneuver) in _LANE_CHANGE_LAMPS
      and _at_road_edge(turn.get('direction'), topology)):
    turn = dict(turn, signalRequested=False, direction='none', reason='atRoadEdge')
  return turn if settings.turn_signal_enabled else out

