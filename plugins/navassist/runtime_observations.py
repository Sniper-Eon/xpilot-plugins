"""Runtime observation assembly, bounded plan cache and status projection."""
from __future__ import annotations
from .navstate import road_kind as classify_road_kind

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


class RuntimeObservations:
  def _plan_lanes(self, nav, now_ns):
    """PLAN_LANES_HOLD：只用于规划输入的车道列表保持。"""
    from .runtime import PLAN_LANES_HOLD_S
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

  def read_topology(self, current, model, model_ns, now_ns, can_list, phone_lane_estimate,
                    topology_builder, nav_builder, recording_observer):
    self.oem.update(can_list, now_ns)
    oem = self.oem.payload(now_ns)
    topology = topology_builder(model, now_ns, model_ns)
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
    nav = nav_builder(current, now_ns, oem_nav_route_active=oem['navRouteActive'])
    # Read-only shadow diagnostics.  Deliberately not used by any downstream
    # planning, intent, lamp or lane-change input.
    _recording = recording_observer(nav, getattr(self, '_recording_road_key', None))
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
    return nav, topology, oem
