"""Bounded current-road lane-count memory, independent of action planning gates."""
from __future__ import annotations

MAX_AGE_NS = 90_000_000_000
CONFIRM_NS = 500_000_000
MAX_CALLBACK_AGE_MS = 10_000


class RoadTotalMemory:
  def __init__(self):
    self.total = None
    self.reference_total = None
    self.minimum_stamp = 0
    self.context = None
    self.road = ''
    self.confirmed_ns = None
    self.candidate = None
    self.since_ns = None
    self.last_observation = None
    self.last_ns = None

  def reset(self):
    self.__init__()

  def update(self, current, nav, now_ns, *, enabled, layout_allowed):
    snap = getattr(current, 'snapshot', None)
    active = bool(enabled and snap is not None and not current.is_stale(now_ns)
                  and nav.get('routeActive') and nav.get('mode') == 'realtime')
    if not active or (self.last_ns is not None and now_ns < self.last_ns):
      self.reset()
      if not active:
        return None
    context = (nav.get('sessionId'), nav.get('routeRevision'))
    road = str(getattr(snap, 'current_road', '') or '').strip()
    # ROAD_NAME_NO_RESET：道路名切换（桥→路、匝道→主路）不再清空车道数记忆。
    # 之前每过一次路名边界就重置，导致车道上限永远确认不下来。
    if self.context != context:
      floor = getattr(snap, 'source_wall_time_ms', 0) if self.context is not None else 0
      self.reset()
      self.minimum_stamp = floor
    self.context, self.last_ns = context, now_ns
    if road:
      self.road = road
    if self.confirmed_ns is not None and now_ns - self.confirmed_ns > MAX_AGE_NS:
      self.total = None
      self.confirmed_ns = None
      self.candidate, self.since_ns = None, None
    lanes = nav.get('lanes') or ()
    n = len(lanes)
    stamp = getattr(snap, 'lane_guidance_observed_at_ms', 0)
    source_ms = getattr(snap, 'source_wall_time_ms', 0)
    age_ms = source_ms - stamp + current.age_ms(now_ns)
    same_layout = (self.reference_total is None or n == self.reference_total
                   or nav.get('maneuver') in ('none', 'straight'))
    # LANE_COUNT_INDEPENDENT：车道数和「引导是否新鲜」是两件事。
    # 高德引导回调稀疏（实测 14 秒才来一次），行驶中 nav.valid 常为 False，
    # 但车道列表本身是新鲜的 —— 不能因此丢掉车道数。
    qualified = bool(layout_allowed and same_layout and n in range(2, 17)
                     and getattr(snap, 'lane_guidance_present', False)
                     and 0 < stamp <= source_ms and stamp >= self.minimum_stamp
                     and 0 <= age_ms <= MAX_CALLBACK_AGE_MS)
    if not qualified:
      self.candidate, self.since_ns = None, None
      return self.total
    observed_ns = now_ns - int(age_ms * 1_000_000)
    observation = (context, road or self.road, stamp)
    if self.total == n:
      if observation != self.last_observation:
        self.confirmed_ns = max(self.confirmed_ns or observed_ns, observed_ns)
      self.last_observation = observation
      self.candidate, self.since_ns = None, None
      return self.total
    if self.candidate != n:
      self.candidate, self.since_ns = n, now_ns
    elif now_ns - self.since_ns >= CONFIRM_NS:
      self.total, self.confirmed_ns = n, observed_ns
      self.reference_total = n
      self.last_observation = observation
      self.candidate, self.since_ns = None, None
    return self.total
