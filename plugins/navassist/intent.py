"""Adapt plugin messages to the verified legacy preparation state machines.

Only fresh absolute evidence translates map indices. Same-direction edge fallback
remains separate evidence and inherits the bounded source-continuity checks.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace as N

from .coordinator import NavLaneIntentCoordinator, NavTurnSignalCoordinator
from .intent_types import LaneIntentDirection, LaneTopologyInput, LaneVehicleInput, NavTurnPlan, ObservedLaneChangeState
from .planning import build_lane_plan, lane_alignment_may_start, RELATIVE_ROUTE_MANEUVERS


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


def lane_plan(nav, topology, settings, *, v_ego):
  n = navigation(nav)
  count, ego = int(topology.get('visibleLaneCount', 0)), int(topology.get('egoLaneIndexFromLeft', -1))
  absolute = topology.get('absoluteEgoIndex')
  if type(absolute) is not int:
    absolute = None
  core = build_lane_plan(n, N(visibleLaneCount=count, egoLaneIndexFromLeft=ego),
                         healthy=True, settings=settings, amap_ego_index=absolute)
  target = NavLaneIntentCoordinator._target(core, ego) if core.valid else None
  direction = (NavLaneIntentCoordinator._relative_direction(core) or
               NavLaneIntentCoordinator._direction(ego, target)) if target is not None else LaneIntentDirection.none
  # The facade's target is adjacent; the core retains the actual route target.
  adjacent = NavLaneIntentCoordinator._adjacent_target_index(ego, direction) if direction else -1
  return LanePlan('left' if direction == LaneIntentDirection.left else 'right' if direction else 'none',
                  adjacent, -1, 'edgeFallback' if core.heuristic else 'absoluteLane', absolute is not None,
                  core, topology, v_ego)


def payload(intent, nav):
  return dict(valid=bool(nav.get('linked', nav.get('valid'))), sessionId=str(nav.get('sessionId', '')),
              routeRevision=int(nav.get('routeRevision', 0)), maneuverEventId=int(nav.get('maneuverEventId', 0)),
              signalRequested=intent.signal_requested, direction=intent.direction.name,
              targetLaneIndex=intent.target_lane_index, spLaneChangeReady=intent.lane_change_ready,
              laneChangeAllowed=intent.lane_change_ready, reason=intent.reason, requestId=intent.request_id,
              forkNow=False, allowUnknownCrossing=False, ignoreSolidBoundary=False,
              signalPurpose='nativeLaneChange' if nav.get('maneuver') in ('slight_left', 'slight_right')
                and intent.target_lane_index < 0 else 'lanePreparation' if nav.get('maneuver') in
                ('merge_left', 'merge_right', 'exit_left', 'exit_right', 'ramp_left', 'ramp_right')
                or intent.target_lane_index >= 0 else 'junction')


class TurnSignalCoordinator:
  def __init__(self):
    self.core = NavTurnSignalCoordinator()

  def reset(self):
    self.core = NavTurnSignalCoordinator()

  def update(self, nav, *, speed_mps, now_ns, lookahead_time_s=8., turn_geometry_active=False):
    n = navigation(nav)
    plan = NavTurnPlan(bool(nav.get('linked', nav.get('valid', False))) and not nav.get('stale', False),
                       n.sessionId, n.routeRevision, n.maneuverEventId, n.maneuver, n.maneuverDistanceM)
    return payload(self.core.update(plan, speed_mps=speed_mps, now_ns=now_ns,
                                   lookahead_time_s=lookahead_time_s,
                                   turn_geometry_active=turn_geometry_active), nav)


class LaneIntentCoordinator:
  def __init__(self, *, max_changes=5):
    self.max_changes = max_changes
    self.core = NavLaneIntentCoordinator(max_changes=max_changes)
    self._completed_relative_event = None
    self._owned_lane_event = None

  def reset(self):
    self.core = NavLaneIntentCoordinator(max_changes=self.max_changes)
    self._completed_relative_event = None
    self._owned_lane_event = None

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
    result = self.core.update(plan.core, topology, vehicle, now_ns=now_ns,
                              allow_new_lane_change=allow_new_lane_change)
    event = (nav.get('sessionId'), nav.get('routeRevision'), nav.get('maneuverEventId'))
    if plan.core.relative_change_limit == 1 and result.reason == 'laneChangeObserved':
      self._completed_relative_event = event
    if result.signal_requested:
      self._owned_lane_event = event
    return dict(payload(result, nav), relativeStepComplete=self._completed_relative_event == event,
                laneRequestOwned=self._owned_lane_event == event)


def build_intent(nav, topology, *, settings, v_ego, now_ns, left_blocked, right_blocked,
                 blindspot_left, blindspot_right, lateral_active, turns, lanes,
                 left_blinker=False, right_blinker=False, brake_pressed=False, gas_pressed=False,
                 steering_pressed=False, model_state='off', model_direction='none', turn_geometry_active=False):
  turn = turns.update(nav, speed_mps=v_ego, now_ns=now_ns, lookahead_time_s=settings.signal_lead_time_s,
                      turn_geometry_active=turn_geometry_active)
  n = navigation(nav)
  intersection = n.maneuver in ('turnLeft', 'sharpLeft', 'uTurnLeft', 'turnRight', 'sharpRight', 'uTurnRight')
  approaching = bool(intersection and turn['signalRequested'])
  plan = lane_plan(nav, topology, settings, v_ego=v_ego)
  out = lanes.update(nav, plan, now_ns=now_ns, topology_valid=bool(topology.get('valid')),
    left_blocked=left_blocked, right_blocked=right_blocked,
    blindspot_left=blindspot_left, blindspot_right=blindspot_right, lateral_active=lateral_active,
    left_blinker=left_blinker, right_blinker=right_blinker, brake_pressed=brake_pressed,
    gas_pressed=gas_pressed, steering_pressed=steering_pressed, model_state=model_state,
    model_direction=model_direction, allow_new_lane_change=n.maneuverDistanceM > 0 and not approaching)
  if (n.maneuver in RELATIVE_ROUTE_MANEUVERS and topology.get('absoluteEgoIndex') is None
      and out.get('relativeStepComplete')):
    out.update(signalRequested=False, spLaneChangeReady=False, laneChangeAllowed=False, reason='heuristicChangeLimit')
    return out
  if out['signalRequested']:
    return out
  if settings.turn_signal_enabled and turn['signalRequested']:
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
  return turn if settings.turn_signal_enabled else out
