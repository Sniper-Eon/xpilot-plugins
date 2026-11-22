"""Geometry: WGS-84 -> GCJ-02, local tangent-plane projection, route projection.

Sign convention used everywhere in lanenav: lateral offset is POSITIVE TO THE
RIGHT of the route's direction of travel (same as modelV2's right-positive y).
"""
from __future__ import annotations

import math

EARTH_R = 6378137.0

# GCJ-02 offset uses the Krasovsky 1940 ellipsoid (public, widely documented formula).
_KRAS_A = 6378245.0
_KRAS_EE = 0.00669342162296594323


def _in_china(lat: float, lon: float) -> bool:
  return 73.66 <= lon <= 135.05 and 3.86 <= lat <= 53.55


def _dlat(x: float, y: float) -> float:
  r = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
  r += (20.0 * math.sin(6.0 * math.pi * x) + 20.0 * math.sin(2.0 * math.pi * x)) * 2.0 / 3.0
  r += (20.0 * math.sin(math.pi * y) + 40.0 * math.sin(math.pi * y / 3.0)) * 2.0 / 3.0
  r += (160.0 * math.sin(math.pi * y / 12.0) + 320.0 * math.sin(math.pi * y / 30.0)) * 2.0 / 3.0
  return r


def _dlon(x: float, y: float) -> float:
  r = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
  r += (20.0 * math.sin(6.0 * math.pi * x) + 20.0 * math.sin(2.0 * math.pi * x)) * 2.0 / 3.0
  r += (20.0 * math.sin(math.pi * x) + 40.0 * math.sin(math.pi * x / 3.0)) * 2.0 / 3.0
  r += (150.0 * math.sin(math.pi * x / 12.0) + 300.0 * math.sin(math.pi * x / 30.0)) * 2.0 / 3.0
  return r


def wgs84_to_gcj02(lat: float, lon: float) -> tuple[float, float]:
  """Convert a u-blox WGS-84 fix to GCJ-02 (the frame Amap route geometry uses)."""
  if not _in_china(lat, lon):
    return lat, lon
  dlat = _dlat(lon - 105.0, lat - 35.0)
  dlon = _dlon(lon - 105.0, lat - 35.0)
  rad = math.radians(lat)
  m = 1.0 - _KRAS_EE * math.sin(rad) ** 2
  sm = math.sqrt(m)
  dlat = dlat * 180.0 / ((_KRAS_A * (1.0 - _KRAS_EE)) / (m * sm) * math.pi)
  dlon = dlon * 180.0 / (_KRAS_A / sm * math.cos(rad) * math.pi)
  return lat + dlat, lon + dlon


class LocalFrame:
  """Equirectangular tangent plane around an origin; accurate to cm over a few km."""

  def __init__(self, lat0: float, lon0: float):
    self.lat0, self.lon0 = lat0, lon0
    self._kx = math.cos(math.radians(lat0)) * EARTH_R * math.pi / 180.0
    self._ky = EARTH_R * math.pi / 180.0

  def to_xy(self, lat: float, lon: float) -> tuple[float, float]:
    return (lon - self.lon0) * self._kx, (lat - self.lat0) * self._ky  # x=east, y=north

  def to_latlon(self, x: float, y: float) -> tuple[float, float]:
    return self.lat0 + y / self._ky, self.lon0 + x / self._kx


def bearing_of(dx: float, dy: float) -> float:
  """Compass bearing (deg, 0=north, clockwise) of an east/north vector."""
  return math.degrees(math.atan2(dx, dy)) % 360.0


def angle_diff(a: float, b: float) -> float:
  return (a - b + 180.0) % 360.0 - 180.0


class Projection:
  __slots__ = ("s", "lateral", "seg_bearing", "seg_index", "dist")

  def __init__(self, s, lateral, seg_bearing, seg_index, dist):
    self.s, self.lateral, self.seg_bearing, self.seg_index, self.dist = s, lateral, seg_bearing, seg_index, dist


class Route:
  """A route polyline in GCJ-02 (as delivered by Amap) projected into a local frame."""

  def __init__(self, points_gcj: list[tuple[float, float]]):
    if len(points_gcj) < 2:
      raise ValueError("route needs >= 2 points")
    self.frame = LocalFrame(*points_gcj[0])
    self.xy = [self.frame.to_xy(lat, lon) for lat, lon in points_gcj]
    self.cum = [0.0]
    for (x0, y0), (x1, y1) in zip(self.xy, self.xy[1:]):
      self.cum.append(self.cum[-1] + math.hypot(x1 - x0, y1 - y0))

  @property
  def length(self) -> float:
    return self.cum[-1]

  def project(self, lat_gcj: float, lon_gcj: float, bearing_deg: float | None = None,
              s_hint: float | None = None, window_m: float = 200.0,
              max_heading_err: float = 60.0) -> Projection | None:
    """Closest point on the route; optionally gated by heading and an along-track hint.

    Heading gating stops a fix from snapping onto the opposite carriageway or a
    parallel ramp segment that the route passes twice.
    """
    px, py = self.frame.to_xy(lat_gcj, lon_gcj)
    best = None
    for i, ((x0, y0), (x1, y1)) in enumerate(zip(self.xy, self.xy[1:])):
      if s_hint is not None and (self.cum[i + 1] < s_hint - window_m or self.cum[i] > s_hint + window_m):
        continue
      dx, dy = x1 - x0, y1 - y0
      L2 = dx * dx + dy * dy
      if L2 <= 0:
        continue
      seg_b = bearing_of(dx, dy)
      if bearing_deg is not None and abs(angle_diff(bearing_deg, seg_b)) > max_heading_err:
        continue
      t = max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / L2))
      cx, cy = x0 + t * dx, y0 + t * dy
      d = math.hypot(px - cx, py - cy)
      if best is None or d < best.dist:
        L = math.sqrt(L2)
        # cross product sign: positive when the point is to the RIGHT of travel
        lateral = ((px - x0) * dy - (py - y0) * dx) / L
        best = Projection(self.cum[i] + t * L, lateral, seg_b, i, d)
    return best

  def point_at(self, s: float, lateral: float = 0.0) -> tuple[float, float]:
    """GCJ lat/lon at along-track s with a right-positive lateral offset (for simulation)."""
    s = max(0.0, min(self.length, s))
    for i in range(len(self.cum) - 1):
      if self.cum[i + 1] >= s:
        break
    (x0, y0), (x1, y1) = self.xy[i], self.xy[i + 1]
    L = max(1e-9, self.cum[i + 1] - self.cum[i])
    t = (s - self.cum[i]) / L
    ux, uy = (x1 - x0) / L, (y1 - y0) / L
    # right normal of (ux,uy) in east/north coords is (uy, -ux)
    x = x0 + t * (x1 - x0) + lateral * uy
    y = y0 + t * (y1 - y0) - lateral * ux
    return self.frame.to_latlon(x, y)


def gcj02_to_wgs84(lat: float, lon: float) -> tuple[float, float]:
  """Iterative inverse of wgs84_to_gcj02 (sub-centimetre after a few iterations)."""
  wlat, wlon = lat, lon
  for _ in range(6):
    glat, glon = wgs84_to_gcj02(wlat, wlon)
    wlat += lat - glat
    wlon += lon - glon
  return wlat, wlon
