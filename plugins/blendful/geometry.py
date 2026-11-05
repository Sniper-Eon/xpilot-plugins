"""Shared lane-center geometry for control and the road overlay."""
from __future__ import annotations

import numpy as np

LANE_WIDTH_DEFAULT = 3.6
LANE_WIDTH_CLIP = (2.8, 4.5)
LOOKAHEAD_TIME = 1.5
MIN_LOOKAHEAD = 10.0
MIN_SPEED = 5.0
LINE_STD = (0.2, 0.6)


def _curve(line):
  try:
    x = np.asarray(line.x, dtype=np.float32)
    y = np.asarray(line.y, dtype=np.float32)
  except (AttributeError, TypeError, ValueError):
    return None
  if x.size < 2 or x.size != y.size or not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
    return None
  if np.any(np.diff(x) <= 0):
    return None
  return x, y


def y_at_x(line, x_m: float) -> float | None:
  curve = _curve(line)
  if curve is None:
    return None
  x, y = curve
  if x_m < x[0] or x_m > x[-1]:
    return None
  return float(np.interp(x_m, x, y))


def center_y(model, x_m: float) -> tuple[float, float, float] | None:
  """Return (center_y, left_prob, right_prob) when the ego lane is usable."""
  try:
    lines = list(model.laneLines)
    probs = [float(p) for p in model.laneLineProbs]
    stds = [float(s) for s in model.laneLineStds]
  except (AttributeError, TypeError, ValueError):
    return None
  if len(lines) < 4 or len(probs) < 4 or len(stds) < 4:
    return None
  if not all(0.0 <= p <= 1.0 and 0.0 <= s <= 1.0 for p, s in zip(probs[1:3], stds[1:3])):
    return None
  left, right = y_at_x(lines[1], x_m), y_at_x(lines[2], x_m)
  if left is None or right is None or not left < 0.0 < right:
    return None
  width = right - left
  if not LANE_WIDTH_CLIP[0] <= width <= LANE_WIDTH_CLIP[1]:
    return None
  return (left + right) / 2.0, probs[1], probs[2]


def confidence(prob: float, std: float) -> float:
  return float(np.clip(prob * np.interp(std, LINE_STD, (1.0, 0.0)), 0.0, 1.0))


def lane_center(model, v_ego: float) -> tuple[float, float] | None:
  """Return (blue center-line y in car space, trust) for the current ego lane."""
  if v_ego < MIN_SPEED:
    return None
  lookahead = max(v_ego * LOOKAHEAD_TIME, MIN_LOOKAHEAD)
  center = center_y(model, lookahead)
  if center is None:
    return None
  y, lp, rp = center
  # Confidence already includes each lane probability. Apply it once, then
  # combine the two independent lines; multiplying the probabilities again
  # collapses trust (0.78/0.08 became 0.024 and never reached the 0.05 draw gate).
  left = confidence(lp, float(model.laneLineStds[1]))
  right = confidence(rp, float(model.laneLineStds[2]))
  trust = left + right - left * right
  return y, float(np.clip(trust, 0.0, 1.0))
