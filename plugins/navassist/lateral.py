"""Lateral offset of the car from the navigation route, in metres.

Diagnostic only: it feeds the log so the geometry model (road centre = the
boundary between the middle lanes) can be validated against real drives before
any of it is allowed to touch the lane number.
"""
from __future__ import annotations

import math

EARTH_M_PER_DEG = 111_320.0


def _to_local(lat0: float, lon0: float, lat: float, lon: float) -> tuple[float, float]:
  """Equirectangular projection, good to millimetres over a few hundred metres."""
  y = (lat - lat0) * EARTH_M_PER_DEG
  x = (lon - lon0) * EARTH_M_PER_DEG * math.cos(math.radians(lat0))
  return x, y


def offset_m(points, lat: float, lon: float, *, max_points: int = 4000) -> float | None:
  """Signed perpendicular distance from ``points`` (lat, lon pairs), + = right of travel.

  The route is ordered along the direction of travel, so the cross product of the
  segment direction with the car vector is positive when the car sits on the right.
  """
  if not points:
    return None
  pts = list(points)[:max_points]
  if len(pts) < 2:
    return None
  best = None
  for (alat, alon), (blat, blon) in zip(pts, pts[1:]):
    ax, ay = _to_local(lat, lon, alat, alon)
    bx, by = _to_local(lat, lon, blat, blon)
    dx, dy = bx - ax, by - ay
    seg2 = dx * dx + dy * dy
    if seg2 <= 1e-9:
      continue
    t = -(ax * dx + ay * dy) / seg2
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    px, py = ax + t * dx, ay + t * dy
    dist2 = px * px + py * py
    if best is None or dist2 < best[0]:
      # cross product z = dx*py - dy*px > 0 means the car is to the right of this segment
      cross = dx * py - dy * px
      best = (dist2, math.copysign(math.sqrt(dist2), cross if cross != 0.0 else 1.0))
  return None if best is None else best[1]


def route_points(geometry):
  """Return WGS-84 (lat, lon) pairs from a RouteGeometry, or () when unusable."""
  if geometry is None:
    return ()
  try:
    pts = getattr(geometry, 'wgs84_points', ()) or ()
    if pts:
      return pts
    return getattr(geometry, 'points', ()) or ()
  except Exception:
    return ()


class RouteOffsetTracker:
  """Cursor-limited offset tracking so the projection stays cheap at 20 Hz."""

  def __init__(self, window: int = 60):
    self.window = window
    self.index = 0
    self.points = ()

  def reset(self, points=()) -> None:
    self.index = 0
    self.points = tuple(points or ())

  def update(self, points, lat: float, lon: float) -> float | None:
    pts = tuple(points or ())
    if pts != self.points:
      self.points = pts
      self.index = 0
    if len(pts) < 2:
      return None
    best_index, best = None, None
    lo = max(0, self.index - self.window)
    hi = min(len(pts) - 2, self.index + self.window)
    for i in range(lo, hi + 1):
      d = _segment_offset(pts[i], pts[i + 1], lat, lon)
      if d is not None and (best is None or abs(d) < abs(best)):
        best, best_index = d, i
    if best_index is None:
      # 光标搜索失败（跳变/新路线）→ 全量扫一次
      for i in range(len(pts) - 1):
        d = _segment_offset(pts[i], pts[i + 1], lat, lon)
        if d is not None and (best is None or abs(d) < abs(best)):
          best, best_index = d, i
    if best_index is not None:
      self.index = best_index
    return best


def _segment_offset(a, b, lat: float, lon: float) -> float | None:
  (alat, alon), (blat, blon) = a, b
  ax, ay = _to_local(lat, lon, alat, alon)
  bx, by = _to_local(lat, lon, blat, blon)
  dx, dy = bx - ax, by - ay
  seg2 = dx * dx + dy * dy
  if seg2 <= 1e-9:
    return None
  t = -(ax * dx + ay * dy) / seg2
  t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
  px, py = ax + t * dx, ay + t * dy
  dist = math.hypot(px, py)
  cross = dx * py - dy * px
  return math.copysign(dist, cross if cross != 0.0 else 1.0)


def route_bearing_deg(points, index) -> float | None:
  """Compass bearing of the tracked route segment, degrees clockwise from north."""
  if not points or not isinstance(index, int) or index < 0 or index >= len(points) - 1:
    return None
  (alat, alon), (blat, blon) = points[index], points[index + 1]
  x, y = _to_local(alat, alon, blat, blon)
  if x * x + y * y <= 1e-9:
    return None
  return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0
