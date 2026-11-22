"""GPS lateral step as auxiliary lane-change evidence.

On the 11-13 road test the route-relative GPS offset stepped by 2.2-3.8 m across the
car's own lane changes while being smooth otherwise (5 s jitter p50 0.21 m). A step of
about one lane width, with a quiet signal after it and no change of lane count / route
segment in the window, is reported as 'left' / 'right'. It is evidence, not truth: the
pipeline de-duplicates it against the dead-reckoning and car lane-change events.
"""
from __future__ import annotations

from collections import deque


class GpsJumpDetector:
  def __init__(self, lo_m=2.2, hi_m=3.8, pre=(7.0, 4.0), post_s=1.5, quiet_m=0.5, pre_quiet_m=1.0,
               cooldown_s=6.0, max_hacc_m=2.5, max_gap_s=1.0):
    self.lo, self.hi, self.pre, self.post_s = lo_m, hi_m, pre, post_s
    self.quiet, self.pre_quiet, self.cooldown, self.max_hacc = quiet_m, pre_quiet_m, cooldown_s, max_hacc_m
    self.max_gap = max_gap_s
    self.buf = deque()
    self.n = None
    self.last_fire = -1e9

  @staticmethod
  def _median(v):
    v = sorted(v)
    return v[len(v) // 2] if v else None

  def update(self, t, lateral_m, hacc_m=None, lane_count=None):
    if lateral_m is None or (hacc_m is not None and hacc_m > self.max_hacc):
      return None
    if lane_count != self.n:        # new segment / lane layout: polyline may jump, start over
      self.buf.clear()
      self.n = lane_count
    if self.buf and t - self.buf[-1][0] > self.max_gap:   # dropout: do not bridge it
      self.buf.clear()
    self.buf.append((t, lateral_m))
    while self.buf and t - self.buf[0][0] > self.pre[0] + 0.5:
      self.buf.popleft()
    if t - self.last_fire < self.cooldown:
      return None
    pre = [x for tt, x in self.buf if t - self.pre[0] <= tt <= t - self.pre[1]]
    post = [x for tt, x in self.buf if tt >= t - self.post_s]
    if len(pre) < 3 or len(post) < 3:
      return None
    if max(post) - min(post) > self.quiet or max(pre) - min(pre) > self.pre_quiet:
      return None   # both sides of the step must be steady (a swing is not a lane change)
    jump = self._median(post) - self._median(pre)
    if self.lo <= abs(jump) <= self.hi:
      self.last_fire = t
      self.buf.clear()
      return "right" if jump > 0 else "left"
    return None
