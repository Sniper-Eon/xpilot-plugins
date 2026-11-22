"""Cumulative lateral displacement from speed + heading + gyro, relative to the route.

Integrates v * sin(heading - route_bearing). Heading is propagated with the gyro
yaw rate and pulled slowly towards GPS bearing (complementary filter) only when
the car is moving fast enough for GPS bearing to be meaningful. The integral is
leaky (high-pass) so slow drift and route-bearing errors do not accumulate; what
remains is the fast lateral motion of a lane change, which becomes an event.
"""
from __future__ import annotations

import math

from .geo import angle_diff


class LateralDeadReckoner:
  def __init__(self, lane_width_m=3.5, trigger_frac=0.70, leak_tau_s=8.0,
               gps_heading_gain=0.05, min_gps_speed=5.0):
    self.w = lane_width_m
    self.trigger = trigger_frac * lane_width_m
    self.leak_tau = leak_tau_s
    self.k = gps_heading_gain
    self.min_gps_speed = min_gps_speed
    self.heading = None   # deg, compass
    self.lat = 0.0        # leaky cumulative lateral displacement, right positive
    self.total = 0.0      # non-leaky, for diagnostics
    self.t = None

  def update(self, t, speed_mps, route_bearing_deg, yaw_rate_dps=None, gps_bearing_deg=None):
    """Returns 'left' / 'right' when a lane change worth of lateral motion is seen."""
    if self.t is None:
      self.t = t
      self.heading = gps_bearing_deg if gps_bearing_deg is not None else route_bearing_deg
      return None
    dt = max(0.0, min(0.5, t - self.t))
    self.t = t
    if self.heading is None or route_bearing_deg is None or speed_mps is None:
      return None
    if yaw_rate_dps is not None:
      self.heading = (self.heading + yaw_rate_dps * dt) % 360.0  # yaw rate clockwise-positive
    if gps_bearing_deg is not None and speed_mps >= self.min_gps_speed:
      self.heading = (self.heading + self.k * angle_diff(gps_bearing_deg, self.heading)) % 360.0
    if yaw_rate_dps is None and gps_bearing_deg is not None:
      self.heading = gps_bearing_deg
    rel = math.radians(angle_diff(self.heading, route_bearing_deg))
    dy = speed_mps * math.sin(rel) * dt
    self.total += dy
    self.lat = self.lat * math.exp(-dt / self.leak_tau) + dy
    if self.lat >= self.trigger:
      self.lat -= self.w
      return "right"
    if self.lat <= -self.trigger:
      self.lat += self.w
      return "left"
    return None
