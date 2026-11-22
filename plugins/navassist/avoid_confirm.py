"""Avoidance-lane exit confirmation: 2 consecutive matching updates, day or night.

Replaces the planning distance gate for the ABS_STEP (leave-avoidance) signal only.
The 250 / 800 / 640 / 400 m numbers themselves stay in rec_gate / planning for the
two-stage numbering switch and the other recommendation-translation paths.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

NIGHT_FRAMES = 2
DAY_FRAMES = 2
# Civil twilight: sun 6 degrees below the horizon.
CIVIL_TWILIGHT_DEG = -6.0
# Default when the car has no fix: Foshan Chancheng.
DEFAULT_LAT = 23.03
DEFAULT_LON = 113.13


def solar_elevation_deg(when, lat, lon) -> float:
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    utc = when.astimezone(timezone.utc)
    y, m, d = utc.year, utc.month, utc.day
    hour = utc.hour + utc.minute / 60.0 + utc.second / 3600.0 + utc.microsecond / 3.6e9
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + a // 4
    jd = int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + d + b - 1524.5 + hour / 24.0
    n = jd - 2451545.0
    L = (280.460 + 0.9856474 * n) % 360.0
    g = math.radians((357.528 + 0.9856003 * n) % 360.0)
    lam = math.radians(L + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g))
    eps = math.radians(23.439 - 0.0000004 * n)
    ra = math.atan2(math.cos(eps) * math.sin(lam), math.cos(lam))
    dec = math.asin(math.sin(eps) * math.sin(lam))
    gmst = (18.697374558 + 24.06570982441908 * n) % 24.0
    lst = (gmst + float(lon) / 15.0) % 24.0
    ha = math.radians(lst * 15.0 - math.degrees(ra))
    latr = math.radians(float(lat))
    return math.degrees(math.asin(
        math.sin(latr) * math.sin(dec) + math.cos(latr) * math.cos(dec) * math.cos(ha)))


def is_night(now=None, lat=None, lon=None) -> bool:
    when = now if now is not None else datetime.now(timezone.utc)
    el = solar_elevation_deg(when, lat if lat is not None else DEFAULT_LAT,
                             lon if lon is not None else DEFAULT_LON)
    return el < CIVIL_TWILIGHT_DEG


class AvoidanceConfirm:
    def __init__(self):
        self.hits = 0
        self.key = None
        self.need = DAY_FRAMES

    def reset(self):
        self.hits = 0
        self.key = None

    def update(self, in_avoid, key, *, night=False) -> bool:
        self.need = NIGHT_FRAMES if night else DAY_FRAMES
        if not in_avoid:
            self.reset()
            return False
        if key != self.key:
            self.key = key
            self.hits = 1
        else:
            self.hits += 1
        return self.hits >= self.need
