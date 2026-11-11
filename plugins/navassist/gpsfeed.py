"""Vehicle GPS feed for the phone.

The phone's own GNSS drops out in the cabin far more often than the car's
receiver, so the plugin forwards the vehicle fix to the phone in the UDP ack
(``vehicleTelemetry``). The app already prefers a qualified vehicle fix and
falls back to its own GNSS, so this only needs to publish a well-formed fix.

Coordinates must be GCJ-02: the app labels vehicle fixes as GCJ-02 and feeds
them straight into the AMap SDK. openpilot reports WGS-84, so convert here.
"""
from __future__ import annotations

import math
import time

MAX_AGE_MS = 2_000          # the app drops vehicle fixes older than 3 s
MAX_ACCURACY_M = 24.9       # 略低于插件侧 25.0 的门槛，避免卡边界
MIN_ACCURACY_M = 0.2
MAX_SPEED_KPH = 255.0

# Krasovsky ellipsoid constants used by the standard WGS-84 -> GCJ-02 offset.
_A = 6378245.0
_EE = 0.00669342162296594323

_state = {
  "lat": None, "lon": None, "accuracy": None, "speed_kph": None, "bearing": None,
  "stamp_ms": 0, "mono_ns": 0, "valid": False,
}


def _out_of_china(lat: float, lon: float) -> bool:
  return not (72.004 <= lon <= 137.8347 and 0.8293 <= lat <= 55.8271)


def _transform_lat(x: float, y: float) -> float:
  ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
  ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
  ret += (20.0 * math.sin(y * math.pi) + 40.0 * math.sin(y / 3.0 * math.pi)) * 2.0 / 3.0
  ret += (160.0 * math.sin(y / 12.0 * math.pi) + 320.0 * math.sin(y * math.pi / 30.0)) * 2.0 / 3.0
  return ret


def _transform_lon(x: float, y: float) -> float:
  ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
  ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
  ret += (20.0 * math.sin(x * math.pi) + 40.0 * math.sin(x / 3.0 * math.pi)) * 2.0 / 3.0
  ret += (150.0 * math.sin(x / 12.0 * math.pi) + 300.0 * math.sin(x / 30.0 * math.pi)) * 2.0 / 3.0
  return ret


def wgs84_to_gcj02(lat: float, lon: float) -> tuple[float, float]:
  if _out_of_china(lat, lon):
    return lat, lon
  dlat = _transform_lat(lon - 105.0, lat - 35.0)
  dlon = _transform_lon(lon - 105.0, lat - 35.0)
  radlat = lat / 180.0 * math.pi
  magic = math.sin(radlat)
  magic = 1 - _EE * magic * magic
  sqrtmagic = math.sqrt(magic)
  dlat = (dlat * 180.0) / ((_A * (1 - _EE)) / (magic * sqrtmagic) * math.pi)
  dlon = (dlon * 180.0) / (_A / sqrtmagic * math.cos(radlat) * math.pi)
  return lat + dlat, lon + dlon


def update(gps, now_mono_ns: int) -> None:
  """Feed one ``gpsLocationExternal`` sample. Anything unusable marks the fix missing."""
  try:
    lat = float(gps.latitude)
    lon = float(gps.longitude)
    acc = float(gps.horizontalAccuracy)
    stamp = int(gps.unixTimestampMillis)
  except Exception:
    _state.update(valid=False)
    return
  now_wall_ms = time.time() * 1000.0
  age_ms = now_wall_ms - stamp if stamp > 0 else 1e9
  # 精度不设硬门槛：App 的 accuracyValue 只接受 0.2~25.2，超了就截断上报，
  # 否则室内 26-40 米会让车辆定位整段消失，App 退回没星的手机 GPS。
  usable = (math.isfinite(lat) and math.isfinite(lon) and abs(lat) > 0.01 and abs(lon) > 0.01
            and math.isfinite(acc) and acc > 0.0 and 0 <= age_ms < MAX_AGE_MS
            and not issue_flags(gps))
  if not usable:
    _state.update(valid=False)
    return
  glat, glon = wgs84_to_gcj02(lat, lon)
  speed_kph = max(0.0, min(MAX_SPEED_KPH, float(getattr(gps, "speed", 0.0) or 0.0) * 3.6))
  bearing = float(getattr(gps, "bearingDeg", 0.0) or 0.0) % 360.0
  _state.update(lat=glat, lon=glon, accuracy=max(MIN_ACCURACY_M, min(MAX_ACCURACY_M, acc)),
                speed_kph=speed_kph, bearing=bearing, stamp_ms=stamp,
                mono_ns=int(now_mono_ns), valid=True)


def issue_flags(gps) -> bool:
  """Bit 0/1 of the u-blox fix flags mean "no fix"; anything else is usable."""
  try:
    return (int(gps.flags) & 0x1) == 0
  except Exception:
    return True


def telemetry(now_mono_ns: int) -> dict | None:
  """Return the ``vehicleTelemetry`` object, or None when there is no fresh fix."""
  s = _state
  fresh = bool(s["valid"] and s["mono_ns"] and 0 <= now_mono_ns - s["mono_ns"] <= MAX_AGE_MS * 1_000_000)
  if not fresh:
    return {"gpsStatus": "missing", "latitude": None, "longitude": None, "accuracyValue": None,
            "hdop": None, "headingDeg": None, "speedValue": None,
            "mapAvailable": True, "controllerHealth": None, "alcState": None, "forkState": None,
            "abortReason": None, "navAvailable": True, "navUsage": None, "autosteerHealth": None,
            "plannerState": None, "navDistanceM": None}
  age_ms = int(max(0, min(2400, time.time() * 1000.0 - s["stamp_ms"])))
  return {
    "gpsStatus": "observed",
    "latitude": round(float(s["lat"]), 7),
    "longitude": round(float(s["lon"]), 7),
    "accuracyValue": round(float(s["accuracy"]), 2),
    "hdop": 1.0,
    "headingDeg": round(float(s["bearing"]), 2),
    "speedValue": round(float(s["speed_kph"]), 2),
    "mapAvailable": True, "controllerHealth": None, "alcState": None, "forkState": None,
    "abortReason": None, "navAvailable": True, "navUsage": None, "autosteerHealth": None,
    "plannerState": None, "navDistanceM": None,
    "gpsTimeMs": int(s["stamp_ms"]),
    "gpsTimeAgeMs": age_ms,
    "gpsPositionAgeMs": age_ms,
    "gpsMotionAgeMs": age_ms,
  }
