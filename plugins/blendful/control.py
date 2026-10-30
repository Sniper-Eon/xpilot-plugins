"""Blendful lateral correction, adapted from sunnypilot #2073 (MIT)."""
from __future__ import annotations

import math

import numpy as np
from openpilot.cereal import log
from openpilot.common.realtime import DT_MDL

from .geometry import LOOKAHEAD_TIME, MIN_LOOKAHEAD, MIN_SPEED, lane_center

MAX_CORRECTION = 0.02  # curvature; host also caps total correction at 0.5 m/s^2
TRUST_RELEASE = 2.0 / 5.0 ** 2


def _y_at(line, x_m: float) -> float | None:
  try:
    x = np.asarray(line.x, dtype=np.float64)
    y = np.asarray(line.y, dtype=np.float64)
  except (AttributeError, TypeError, ValueError):
    return None
  if x.size < 2 or x.size != y.size or not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
    return None
  if np.any(np.diff(x) <= 0) or x_m < x[0] or x_m > x[-1]:
    return None
  return float(np.interp(x_m, x, y))


class BlendfulCorrection:
  def __init__(self, params):
    self.params = params
    self._correction = 0.0
    self._trust = 0.0

  def _enabled(self) -> bool:
    try:
      return bool(self.params.get_bool('ExtBlendfulEnabled'))
    except Exception:
      return False

  def update(self, sm, v_ego: float, curvature: float) -> float | None:
    if not self._enabled() or v_ego < MIN_SPEED:
      self._correction = self._trust = 0.0
      return None
    try:
      model = sm['modelV2']
      meta = model.meta
    except (KeyError, AttributeError, TypeError):
      return None
    if meta.laneChangeState != log.LaneChangeState.off:
      self._correction = self._trust = 0.0
      return None

    target = lane_center(model, v_ego)
    if target is None:
      return None
    center, trust = target
    lookahead = max(v_ego * LOOKAHEAD_TIME, MIN_LOOKAHEAD)
    try:
      plan_x = np.asarray(model.position.x, dtype=np.float64)
      plan_y = np.asarray(model.position.y, dtype=np.float64)
      plan = float(np.interp(lookahead, plan_x, plan_y))
    except (AttributeError, TypeError, ValueError):
      return None
    # Curvature that moves the plan y to the lane center at the lookahead point.
    dk = 2.0 * (center - plan) / (lookahead * lookahead)
    dk = float(np.clip(dk, -MAX_CORRECTION, MAX_CORRECTION))
    self._trust += (np.clip(trust, 0.0, 1.0) - self._trust) * DT_MDL / (1.5 + DT_MDL)
    desired = self._trust * dk
    release = TRUST_RELEASE * DT_MDL
    self._correction = float(np.clip(desired, self._correction - release, self._correction + release))
    if not math.isfinite(self._correction) or self._trust < 0.05:
      return None
    return curvature + self._correction
