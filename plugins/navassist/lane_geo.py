"""Geometric lane matching, the way a map matcher does it.

The phone's lane-level navigation projects the trajectory onto per-lane
centre lines. We have no HD map, so the geometry is synthesised:

  * the navigation route is the reference line,
  * the road centre is the boundary between the middle lanes (owner's rule),
  * lane centres are equally spaced by the camera-measured lane width,
  * the route sits on the centre of the lanes AMap recommends for this route,
    which is where AMap draws it.

That is a deterministic nearest-centre match with hysteresis, no probability.
Everything it cannot resolve (missing lane width, no route, junction) is
reported as unknown instead of guessed.
"""
from __future__ import annotations

from collections import deque

LANE_WIDTH_DEFAULT_M = 3.4
LANE_WIDTH_MIN_M = 2.4
LANE_WIDTH_MAX_M = 4.6
SWITCH_MARGIN_M = 0.45       # must be this far past the boundary to change lane
MEDIAN_FRAMES = 5            # 0.5 s at 10 Hz: kills single-sample GNSS spikes
MIN_FRAMES = 3               # need this many samples before trusting the median
CONFIRM_NS = 250_000_000     # a new lane must persist this long before switching
COUNT_STABLE_NS = 800_000_000  # AMap lane count must be stable this long before we adopt it
BIAS_STABLE_NS = 800_000_000   # route bias must be stable this long before we adopt it
ENTER_JUNCTION_M = 40.0      # inside this distance the geometry is unreliable
JUNCTION_HOLD_M = 1.6        # lateral drift under this means "kept the lane"
MAX_OFFSET_M = 25.0          # route/position mismatch guard
SIGMA_REF_M = 1.7            # reference GNSS sigma for confidence scaling


def _clamp(v, lo, hi):
  return lo if v < lo else (hi if v > hi else v)


def lane_centers(lane_count: int, width_m: float) -> list[float]:
  """Centres relative to the road centre line, left to right."""
  if lane_count < 1:
    return []
  w = _clamp(width_m, LANE_WIDTH_MIN_M, LANE_WIDTH_MAX_M)
  mid = (lane_count - 1) / 2.0
  return [(k - mid) * w for k in range(lane_count)]


def route_bias(lane_count: int, width_m: float, recommended) -> tuple[float, bool]:
  """Offset of the route from the road centre, from where AMap draws it.

  Returns (bias, assumed). ``assumed`` is True when no recommendation exists and
  the route is taken to be centred on the road.
  """
  centres = lane_centers(lane_count, width_m)
  rec = [i for i in (recommended or ()) if 0 <= i < len(centres)]
  if not rec:
    return 0.0, True
  return sum(centres[i] for i in rec) / len(rec), False


def relative_centres(lane_count: int, width_m: float, recommended) -> tuple[list[float], bool]:
  centres = lane_centers(lane_count, width_m)
  if not centres:
    return [], True
  bias, assumed = route_bias(lane_count, width_m, recommended)
  return [c - bias for c in centres], assumed


class GeometricLaneMatcher:
  """Nearest-centre lane match with hysteresis and junction continuity."""

  def __init__(self):
    self.lane = None
    self._offsets = deque(maxlen=MEDIAN_FRAMES)
    self._pending = None
    self._pending_since = 0
    self._count = None
    self._width = None
    self._raw_count = None
    self._raw_since = 0
    self._bias_raw = None
    self._bias_since = 0
    self._bias = None
    self._raw_count = None
    self._raw_since = 0
    self._bias_raw = None
    self._bias_since = 0
    self._bias = None
    self.reset()

  def reset(self) -> None:
    self.lane = None
    self.junction = False
    self.junction_entry_offset = None
    self._offsets.clear()
    self._pending = None
    self._pending_since = 0
    self._count = None
    self._width = None

  def update(self, *, lane_count, lane_width_m, recommended, offset_m,
             maneuver_distance_m, maneuver, now_ns, sigma_m=None) -> dict:
    out = {"value": None, "confidence": 0.0, "reason": "noGeometry",
           "offsetM": None, "laneWidthM": None, "biasAssumed": True}
    if not isinstance(lane_count, int) or lane_count < 2 or offset_m is None:
      return out
    incoming_count = lane_count
    # COUNT_STABLE：高德车道数在路口/推荐变化时会 3↔4↔5 来回跳，
    # 直接采纳会让车道号跟着跳。要求新值稳定 COUNT_STABLE_NS 才换。
    if self._raw_count != lane_count:
      self._raw_count = lane_count
      self._raw_since = now_ns
    elif now_ns - self._raw_since >= COUNT_STABLE_NS and self._count != lane_count:
      self._count = None      # 允许下面的映射逻辑按新车道数重算
    if self._count is not None and self._raw_count != self._count:
      # 还用旧车道数（未稳定），保持编号空间连续
      lane_count = self._count
    elif self._count is None:
      self._count = lane_count
    if not isinstance(offset_m, (int, float)):
      return out
    width = lane_width_m if isinstance(lane_width_m, (int, float)) and lane_width_m > 0 else LANE_WIDTH_DEFAULT_M
    rel, assumed = relative_centres(lane_count, width, recommended)
    if not rel:
      return out
    # BIAS_STABLE：高德的推荐集合会从"全部推荐"变成"只推荐一侧"，
    # 整条车道格子随之平移 3.4 米 → 车道号凭空跳一条。b 也要求稳定。
    _bias_now = 0.0
    centers_all = lane_centers(lane_count, width)
    _rec = [i for i in (recommended or ()) if 0 <= i < len(centers_all)]
    if _rec:
      _bias_now = sum(centers_all[i] for i in _rec) / len(_rec)
    if self._bias_raw is None or abs(_bias_now - self._bias_raw) > 0.6:
      self._bias_raw = _bias_now
      self._bias_since = now_ns
    elif now_ns - self._bias_since >= BIAS_STABLE_NS and self._bias is None:
      self._bias = self._bias_raw
    if self._bias is not None:
      rel = [c - self._bias for c in centers_all]
    d = float(offset_m)
    if abs(d) > MAX_OFFSET_M:
      out.update(offsetM=round(d, 2), reason="offsetOutOfRange")
      return out
    out.update(offsetM=round(d, 2), laneWidthM=round(_clamp(width, LANE_WIDTH_MIN_M, LANE_WIDTH_MAX_M), 2),
               biasAssumed=assumed)

    inside_junction = isinstance(maneuver_distance_m, (int, float)) and 0.0 <= float(maneuver_distance_m) <= ENTER_JUNCTION_M
    if inside_junction:
      # JUNCTION_CONTINUITY：路口内不重新匹配，只跟踪横向漂移。
      # 漂移小于 JUNCTION_HOLD_M 视为"直着进去还在同一条"，保持上一车道。
      if not self.junction:
        self.junction = True
        self.junction_entry_offset = d
      drift = abs(d - self.junction_entry_offset) if self.junction_entry_offset is not None else None
      if self.lane is not None:
        # 路口内始终给出一个值：漂移小=保持原车道；漂移大=可能换了道但不再重新匹配，
        # 降低置信度即可。之前直接返回未知会让 App 退回手机窗口计数、数字乱跳。
        if drift is None or drift <= JUNCTION_HOLD_M:
          out.update(value=self.lane, confidence=0.75, reason="junctionHeld")
        else:
          out.update(value=self.lane, confidence=0.55, reason="junctionAssumed")
      else:
        out.update(value=None, confidence=0.0, reason="junctionUnknown")
      return out
    self.junction = False
    self.junction_entry_offset = None

    # JUNCTION_REMAP：车道数变化（路段 3 条 ↔ 路口 5 条）时按物理位置换算，
    # 保证编号空间切换后车还在同一条物理车道上；顺带保证 self.lane 不越界。
    if self.lane is not None and (self._count is not None and (self._count != lane_count
                                                              or self._width != width)):
      old_centres = lane_centers(self._count, self._width or width)
      if 0 <= self.lane < len(old_centres):
        physical = old_centres[self.lane]
        new_centres = lane_centers(lane_count, width)
        self.lane = min(range(len(new_centres)), key=lambda i: abs(new_centres[i] - physical))
    self._count, self._width = lane_count, width
    if self.lane is not None and self.lane >= len(rel):
      self.lane = None
      self._pending = None

    # 中值滤波：单帧 GPS 噪声 1.7 米，和半个车道宽同量级，不滤会疯跳。
    self._offsets.append(d)
    d_f = d if len(self._offsets) < MIN_FRAMES else sorted(self._offsets)[len(self._offsets) // 2]
    nearest = min(range(len(rel)), key=lambda i: abs(d_f - rel[i]))
    if self.lane is None:
      self.lane = nearest
      self._pending = None
    elif nearest == self.lane:
      self._pending = None
    else:
      # 当前车道仍能解释偏移 → 不换；否则要求候选车道持续 CONFIRM_NS。
      current_error = abs(d_f - rel[self.lane])
      if current_error > width / 2.0 + SWITCH_MARGIN_M:
        if self._pending != nearest:
          self._pending = nearest
          self._pending_since = now_ns
        elif now_ns - self._pending_since >= CONFIRM_NS:
          self.lane = nearest
          self._pending = None
    error = abs(d_f - rel[self.lane])
    ratio = error / max(width / 2.0, 0.1)
    conf = _clamp(0.95 - 0.5 * ratio, 0.35, 0.95)
    if isinstance(sigma_m, (int, float)) and sigma_m > 0:
      conf = _clamp(conf * _clamp(SIGMA_REF_M / float(sigma_m), 0.55, 1.0), 0.2, 0.95)
    if self.lane >= incoming_count:
      # 车道数刚变小、还在等待稳定：此时编号超出新空间，报未知比报越界值安全
      out.update(value=None, confidence=0.0, reason="countChanging")
      return out
    out.update(value=self.lane, confidence=round(conf, 2), reason="matched")
    return out
