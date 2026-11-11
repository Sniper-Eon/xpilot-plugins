"""Read modelV2 geometry without requesting or encoding camera images.

modelV2 uses right-positive y; indices run left to right. Geometry alone does
not identify dashed/solid paint or grant permission to cross a boundary.
"""
from __future__ import annotations

import math

PROB_FLOOR = .35
SAMPLE_X_M = 10.
STALE_NS = 150_000_000
MIN_LANE_WIDTH_M = 2.2
MAX_LANE_WIDTH_M = 5.


def _y_at_x(line, x_m):
  try:
    xs, ys = list(line.x), list(line.y)
  except AttributeError:
    try:
      xs, ys = zip(*line)
    except (TypeError, ValueError):
      return None
  if len(xs) != len(ys) or len(xs) < 2:
    return None
  if not all(math.isfinite(float(v)) for v in (*xs, *ys)):
    return None
  if any(b <= a for a, b in zip(xs, xs[1:])):
    return None
  for i, (x0, x1) in enumerate(zip(xs, xs[1:])):
    if x0 <= x_m <= x1:
      return float(ys[i] + (x_m-x0)/(x1-x0)*(ys[i+1]-ys[i]))
  return None


def from_model(model, now_ns: int, model_mono_ns: int) -> dict:
  out = dict(valid=False, stale=True, visibleLaneCount=0, egoLaneIndexFromLeft=-1,
             lanesLeftOfEgo=0, lanesRightOfEgo=0, boundaryCount=0, frameId=-1, ageMs=0.,
             leftNeighborExists=False, rightNeighborExists=False,
             leftRoadEdge=False, rightRoadEdge=False,
             leftCrossingAllowed=False, rightCrossingAllowed=False,
             leftEdgeDetected=False, rightEdgeDetected=False,
             leftEdgeGapM=99.0, rightEdgeGapM=99.0,
             captureMonoNs=int(model_mono_ns), boundaryYs=[])
  if model is None or type(model_mono_ns) is not int or model_mono_ns <= 0:
    return out
  age = now_ns-model_mono_ns
  out.update(stale=not 0 <= age <= STALE_NS, ageMs=max(0, age/1e6))
  if out['stale']:
    return out
  try:
    lines, probs = list(model.laneLines), list(model.laneLineProbs)
    out['frameId'] = int(model.frameId)
    if len(lines) != 4 or len(probs) != 4:
      return out
    ys = []
    for line, prob in zip(lines, probs):
      if not math.isfinite(prob) or not 0 <= prob <= 1:
        return out
      if prob < PROB_FLOOR:
        continue
      y = _y_at_x(line, SAMPLE_X_M)
      if y is None:
        return out
      ys.append(y)
    ys.sort()
    if len(ys) < 2:
      return out
    if any(not MIN_LANE_WIDTH_M <= b-a <= MAX_LANE_WIDTH_M for a, b in zip(ys, ys[1:])):
      return out
    ego = next((i for i, (left, right) in enumerate(zip(ys, ys[1:])) if left < 0 < right), -1)
    if ego < 0:
      return out
    edges, stds = list(getattr(model, 'roadEdges', [])), list(getattr(model, 'roadEdgeStds', []))
    physical_left = physical_right = False
    edge_left_ys, edge_right_ys = [], []
    for edge, std in zip(edges, stds):
      y = _y_at_x(edge, SAMPLE_X_M)
      if y is None or not math.isfinite(std) or not 0 <= std <= .8:
        continue
      physical_left |= y < 0 and 0 <= ys[0]-y <= 1.5
      physical_right |= y > 0 and 0 <= y-ys[-1] <= 1.5
      (edge_left_ys if y < 0 else edge_right_ys).append(y)
    out['leftEdgeDetected'] = bool(edge_left_ys)
    out['rightEdgeDetected'] = bool(edge_right_ys)
    # 路沿到最外侧车道线的距离：用来区分「紧贴」和「远在别处」。
    out['leftEdgeGapM'] = (min(ys[0] - y for y in edge_left_ys if y < ys[0])
                           if any(y < ys[0] for y in edge_left_ys) else 99.0)
    out['rightEdgeGapM'] = (min(y - ys[-1] for y in edge_right_ys if y > ys[-1])
                            if any(y > ys[-1] for y in edge_right_ys) else 99.0)
    # SHOULDER_TRIM：模型的路沿落在最外侧那条「车道」里面时，那一段其实是路肩/应急带，
    # 不是可行驶车道。丢掉这条假车道，否则会把本车多算一条（最左车道被数成第 2 条）。
    if len(ys) >= 3:
      if edge_left_ys and ys[0] < min(edge_left_ys, key=abs) < ys[1]:
        ys = ys[1:]
      if len(ys) >= 3 and edge_right_ys and ys[-2] < max(edge_right_ys, key=abs) < ys[-1]:
        ys = ys[:-1]
      ego = next((i for i, (left, right) in enumerate(zip(ys, ys[1:])) if left < 0 < right), -1)
      if ego < 0:
        return out
    count = len(ys)-1
    out.update(valid=True, stale=False, visibleLaneCount=count, egoLaneIndexFromLeft=ego,
               lanesLeftOfEgo=ego, lanesRightOfEgo=count-1-ego, boundaryCount=len(ys), boundaryYs=ys,
               leftNeighborExists=ego > 0, rightNeighborExists=ego < count-1,
               leftRoadEdge=physical_left and ego == 0, rightRoadEdge=physical_right and ego == count-1,
               leftCarriagewayAnchored=physical_left, rightCarriagewayAnchored=physical_right)
  except (AttributeError, TypeError, ValueError, OverflowError):
    return out
  return out
