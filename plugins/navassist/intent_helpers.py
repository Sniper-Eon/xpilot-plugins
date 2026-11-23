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


