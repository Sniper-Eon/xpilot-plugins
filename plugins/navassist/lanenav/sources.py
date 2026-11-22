"""Pluggable position sources. Each adapter turns one raw message into a PositionFix.

Choose the source from measured data, not from a spec sheet: run
``tools/hacc_stats.py`` on real logs and pick the source with the best
availability-weighted lateral sigma. The filter only ever sees PositionFix.
"""
from __future__ import annotations

from dataclasses import dataclass

from .geo import wgs84_to_gcj02


@dataclass
class PositionFix:
  t: float
  lat_gcj: float
  lon_gcj: float
  hacc_m: float            # reported 1-sigma-ish horizontal accuracy (NOT true error)
  bearing_deg: float | None
  speed_mps: float | None
  source: str


def from_ublox(d: dict) -> PositionFix | None:
  """gpsLocationExternal-like dict (WGS-84). flags bit0 = fix valid."""
  try:
    if d.get("flags") is not None and (int(d["flags"]) & 1) == 0:
      return None
    lat, lon, acc = float(d["latitude"]), float(d["longitude"]), float(d["horizontalAccuracy"])
  except (KeyError, TypeError, ValueError):
    return None
  if not (acc > 0 and abs(lat) > 0.01 and abs(lon) > 0.01):
    return None
  glat, glon = wgs84_to_gcj02(lat, lon)
  return PositionFix(float(d.get("t", 0.0)), glat, glon, acc,
                     d.get("bearingDeg"), d.get("speed"), "ublox")


def from_phone(d: dict) -> PositionFix | None:
  """Phone/Amap location, already GCJ-02 (accuracy field in metres)."""
  try:
    return PositionFix(float(d.get("t", 0.0)), float(d["latitude"]), float(d["longitude"]),
                       float(d["accuracy"]), d.get("bearing"), d.get("speed"), "phone")
  except (KeyError, TypeError, ValueError):
    return None


def from_llk(d: dict) -> PositionFix | None:
  """liveLocationKalman-like dict: positionGeodetic [lat,lon,alt] WGS-84 + std (m)."""
  try:
    lat, lon = float(d["positionGeodetic"][0]), float(d["positionGeodetic"][1])
    std = d.get("positionGeodeticStd") or d.get("positionECEFStd")
    acc = max(float(std[0]), float(std[1]))
  except (KeyError, TypeError, ValueError, IndexError):
    return None
  glat, glon = wgs84_to_gcj02(lat, lon)
  return PositionFix(float(d.get("t", 0.0)), glat, glon, acc, d.get("bearingDeg"), d.get("speed"), "llk")


ADAPTERS = {"ublox": from_ublox, "phone": from_phone, "llk": from_llk}
