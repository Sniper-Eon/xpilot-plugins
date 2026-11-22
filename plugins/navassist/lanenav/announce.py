"""Amap-style lane guidance announcements before a junction.

Given the junction lanes (allowed turns + recommended flag), the distance to the
junction and the lane filter output, produce one announcement per distance band:
lane count, each lane's turns, recommended lane(s), and what the driver should do.
"""
from __future__ import annotations

from dataclasses import dataclass

ACTION_ZH = {
  "uturn": "掉头", "left": "左转", "straight": "直行", "right": "右转",
  "slight_left": "向左前方", "slight_right": "向右前方", "bus": "公交专用", "variable": "可变车道",
}
ORDER = ("uturn", "left", "slight_left", "straight", "slight_right", "right", "bus", "variable")
DEFAULT_BANDS_M = (1000.0, 500.0, 200.0, 80.0)
MIN_CONF = 0.55


@dataclass(frozen=True)
class LaneSpec:
  index: int                 # 1..N from the left
  allowed: tuple[str, ...]   # e.g. ("left", "straight")
  recommended: bool = False


def lane_label(spec: LaneSpec) -> str:
  acts = [a for a in ORDER if a in spec.allowed] + [a for a in spec.allowed if a not in ORDER]
  if not acts:
    return "未知"
  return "".join(ACTION_ZH.get(a, a) for a in acts) if len(acts) == 1 else \
    "/".join(ACTION_ZH.get(a, a) for a in acts)


def _fmt_distance(d: float) -> str:
  if d >= 1000:
    return "%.1f公里" % (d / 1000.0) if d % 1000 else "%d公里" % int(d // 1000)
  return "%d米" % int(round(d / 10.0) * 10)


def _ranges(idx: list[int]) -> str:
  out, i = [], 0
  while i < len(idx):
    j = i
    while j + 1 < len(idx) and idx[j + 1] == idx[j] + 1:
      j += 1
    out.append(str(idx[i]) if i == j else "%d-%d" % (idx[i], idx[j]))
    i = j + 1
  return "、".join(out)


def advice(lanes: list[LaneSpec], ego: int | None, prob: float) -> tuple[str, int]:
  """Return (text, signed lane changes needed; negative = to the left)."""
  rec = sorted(l.index for l in lanes if l.recommended)
  if not rec:
    return "", 0
  if ego is None or prob < MIN_CONF:
    return "暂无法确定所在车道，请按推荐车道行驶", 0
  if ego in rec:
    return "您在第%d车道，保持当前车道" % ego, 0
  target = min(rec, key=lambda r: abs(r - ego))
  k = target - ego
  return ("您在第%d车道，请向%s变道%d次" % (ego, "左" if k < 0 else "右", abs(k))), k


def build_text(lanes: list[LaneSpec], distance_m: float, ego: int | None, prob: float) -> str:
  lanes = sorted(lanes, key=lambda l: l.index)
  parts = ["前方%s路口，共%d条车道" % (_fmt_distance(distance_m), len(lanes))]
  parts.append("从左到右：" + "，".join("%d %s" % (l.index, lane_label(l)) for l in lanes))
  rec = [l.index for l in lanes if l.recommended]
  if rec:
    parts.append("推荐第%s车道" % _ranges(rec))
  adv, _ = advice(lanes, ego, prob)
  if adv:
    parts.append(adv)
  return "；".join(parts) + "。"


class Announcer:
  """Emits one announcement per junction per distance band (like the phone app)."""

  def __init__(self, bands_m=DEFAULT_BANDS_M):
    self.bands = tuple(sorted(bands_m, reverse=True))
    self._done: dict = {}

  def update(self, junction_id, lanes: list[LaneSpec], distance_m: float | None,
             ego: int | None, prob: float) -> dict | None:
    if junction_id is None or distance_m is None or not lanes or distance_m < 0:
      return None
    done = self._done.setdefault(junction_id, set())
    band = next((b for b in reversed(self.bands) if distance_m <= b), None)
    if band is None or band in done:
      return None
    # mark this band and every larger band as consumed (do not replay 1 km when we start at 300 m)
    for b in self.bands:
      if b >= band:
        done.add(b)
    adv, k = advice(lanes, ego, prob)
    return dict(junction=junction_id, band_m=band, distance_m=distance_m, ego=ego, prob=prob,
                change=k, text=build_text(lanes, distance_m, ego, prob))
