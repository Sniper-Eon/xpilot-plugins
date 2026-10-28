"""One complete pure navigation cycle; no camera, socket or vehicle actuation."""
from __future__ import annotations

from .blocker import LaneChangeBlocker
from .intent import LaneIntentCoordinator, TurnSignalCoordinator, build_intent
from .navstate import build as build_nav_state
from .oem import OemLaneSignals
from .position import AbsolutePosition
from .topology import from_model


class NavigationRuntime:
  def __init__(self, settings):
    self.settings = settings
    self.oem = OemLaneSignals()
    self.blocker = LaneChangeBlocker()
    self.position = AbsolutePosition()
    self.turns = TurnSignalCoordinator()
    self.lanes = LaneIntentCoordinator(max_changes=settings.max_lane_changes)

  def tick(self, current, model, model_ns, car, cc, now_ns, *, can_list=(), vehicle_fresh=False,
           left_phone=False, right_phone=False, turn_geometry_active=False,
           localization_valid=True):
    self.oem.update(can_list, now_ns)
    oem = self.oem.payload(now_ns)
    topology = from_model(model, now_ns, model_ns)
    nav = build_nav_state(current, now_ns, oem_nav_route_active=oem['navRouteActive'])
    nav['valid'] = bool(nav['valid'] and localization_valid)
    if not localization_valid and nav['reason'] == 'none':
      nav['reason'] = 'localLocalization'
    position = self.position.update(topology, nav, now_ns)
    topology['absoluteEgoIndex'] = position['lane_index']-1 if position['valid'] else None
    left_blocked, right_blocked, reasons = self.blocker.update(oem, topology,
      phone_left=left_phone, phone_right=right_phone)
    oem.update(leftBlocked=left_blocked, rightBlocked=right_blocked, blockReasons=list(reasons))
    for side in ('left', 'right'):
      topology[side+'CrossingAllowed'] = oem[side+'CrossingAllowed'] and not oem[side+'Blocked']
    usable_nav = dict(nav, valid=bool(nav['valid'] and vehicle_fresh),
                      linked=bool(nav.get('linked', nav['valid']) and vehicle_fresh),
                      routeActive=bool(nav.get('routeActive') and vehicle_fresh and self.settings.enabled))
    if not self.settings.enabled:
      usable_nav.update(valid=False, linked=False)
      self.turns.reset()
      self.lanes.reset()
    meta = getattr(model, 'meta', None)
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
      turns=self.turns, lanes=self.lanes)
    return dict(nav=nav, topology=topology, intent=intent, oem=oem, position=position)
