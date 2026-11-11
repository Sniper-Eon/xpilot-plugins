"""Unified absolute lane estimator.

Every source proposes a lane index with a confidence. The caller uses the
highest-confidence proposal; nothing is reported when no source is credible.
Observation-only for now: the runtime logs the estimate next to the legacy
value so the confidence table can be validated on real data before switching.
"""
from __future__ import annotations

# Confidence per source. Keep this table the only place where trust lives.
CONF_LEFT_ADJACENT = 0.95    # model road edge sits on the window's left boundary
CONF_RIGHT_ADJACENT = 0.90   # model road edge sits on the window's right boundary
CONF_POSITION = 0.90         # camera+map anchored absolute index (position.py)
CONF_LEFT_SOLID = 0.60       # left boundary is solid paint near the window edge
CONF_RIGHT_SOLID = 0.70      # right boundary is solid paint near the window edge
CONF_PHONE_RIGHTMOST = 0.60  # phone sees no lane to the right, AMap knows more lanes
CONF_PHONE_COUNT_MATCH = 0.60  # phone lane count equals AMap lane count
CONF_PHONE_LEFT = 0.45       # phone's own left count, AMap total known
CONF_HISTORY = 0.30          # reuse the previous value while it is fresh
CONF_STRONG = 0.85           # above this a two-lane jump is accepted
EDGE_SOLID_MAX_GAP_M = 3.0
HISTORY_STALE_NS = 1_500_000_000


def _int(value, fallback):
  return int(value) if isinstance(value, int) and not isinstance(value, bool) else fallback


def _clamp(value, low, high):
  return max(low, min(high, value))


def estimate(nav, topology, position, phone, line, history, now_ns, road_total=None):
  """Return the absolute lane estimate as a dict.

  nav/topology/position/phone/line/history are plain values; nothing here
  touches openpilot or CAN. ``history`` is ``{"value": int, "ns": int}`` or None.
  """
  nav = nav or {}
  topology = topology or {}
  position = position or {}
  phone = phone or {}
  line = line or {}

  phone_ok = bool(phone.get("valid"))
  phone_number = _int(phone.get("laneNumber"), 0)
  phone_count = _int(phone.get("laneCount"), 0)
  phone_usable = bool(phone_ok and phone_number >= 1 and phone_count >= phone_number)

  lanes = nav.get("lanes") or ()
  amap_total = len(lanes) if isinstance(lanes, (list, tuple)) else 0
  # JUNCTION_LANES：接近路口时高德的 lanes 描述的是「路口那排车道」（常多出左转/待转），
  # 不是当前道路的车道数。用它当总数会把整条路的编号算错，所以优先用稳定观察到的道路总数。
  total = None
  total_source = "none"
  if isinstance(road_total, int) and road_total >= 1:
    total = road_total
    total_source = "road"
  elif amap_total >= 1:
    total = amap_total
    total_source = "amap"
  # 车道总数只信「道路记忆 / 高德」：手机车道数会随视野在 2↔3 之间变化，
  # 拿它当总数正是 3 车道中间来回跳的来源（车主反馈）。
  junction_lanes = bool(isinstance(road_total, int) and road_total >= 1
                        and amap_total >= 1 and abs(amap_total - road_total) >= 2)

  visible = _int(topology.get("visibleLaneCount"), 0)
  ego = _int(topology.get("egoLaneIndexFromLeft"), -1)
  left_solid = _int(line.get("left"), -1) == 1
  right_solid = _int(line.get("right"), -1) == 1
  # 注意：不能用 `x or 99`，0.0 是合法的「紧贴」，会被误判成 99。
  _lg = topology.get("leftEdgeGapM")
  _rg = topology.get("rightEdgeGapM")
  left_gap = 99.0 if _lg is None else float(_lg)
  right_gap = 99.0 if _rg is None else float(_rg)

  candidates = []

  def add(value, source, confidence):
    if value is None:
      return
    if total is not None:
      value = _clamp(value, 0, total - 1)
    elif value < 0:
      return
    candidates.append({"value": int(value), "source": source, "confidence": float(confidence)})

  # S1 camera+map anchored absolute index
  if position.get("valid") and isinstance(position.get("lane_index"), int):
    add(int(position["lane_index"]) - 1, "position", CONF_POSITION)

  # S2 left boundary is the carriageway edge -> window's leftmost lane is AMap #1
  left_adjacent = bool(topology.get("leftCarriagewayAnchored") or topology.get("leftRoadEdge"))
  left_solid_edge = bool(topology.get("leftEdgeDetected") and left_solid
                         and left_gap <= EDGE_SOLID_MAX_GAP_M)
  if left_adjacent or left_solid_edge:
    conf = CONF_LEFT_ADJACENT if left_adjacent else CONF_LEFT_SOLID
    if 0 <= ego:
      add(ego, "leftEdge", conf)
    elif phone_usable:
      add(phone_number - 1, "leftEdgePhone", conf * 0.8)

  # S3/S4 right carriageway edge -> window's rightmost lane is AMap #last
  if total is not None:
    right_adjacent = bool(topology.get("rightCarriagewayAnchored")
                          or topology.get("rightRoadEdge"))
    right_solid_edge = bool(topology.get("rightEdgeDetected") and right_solid
                            and right_gap <= EDGE_SOLID_MAX_GAP_M)
    if right_adjacent or right_solid_edge:
      conf = CONF_RIGHT_ADJACENT if right_adjacent else CONF_RIGHT_SOLID
      if 0 <= ego < max(visible, 1):
        add(total - visible + ego, "rightEdge", conf)
      elif phone_usable:
        add(total - phone_count + (phone_number - 1), "rightEdgePhone", conf * 0.85)

  # S5 phone sees no lane to its right while AMap knows more lanes
  if (not junction_lanes and total is not None and phone_usable
      and phone_number == phone_count and total > phone_count):
    add(total - 1, "phoneRightmost", CONF_PHONE_RIGHTMOST)

  # S6 phone count matches AMap -> its number is the absolute one
  if not junction_lanes and total is not None and phone_usable and phone_count == total:
    add(phone_number - 1, "phoneMatch", CONF_PHONE_COUNT_MATCH)

  # S7 phone left count, only with a known AMap total
  if total is not None and phone_usable:
    add(phone_number - 1, "phoneLeft", CONF_PHONE_LEFT)

  # S8 history keeps the last value briefly
  if history and isinstance(history.get("value"), int) and 0 <= now_ns - _int(history.get("ns"), 0) <= HISTORY_STALE_NS:
    age = now_ns - _int(history.get("ns"), 0)
    decay = 1.0 - (age / HISTORY_STALE_NS)
    add(int(history["value"]), "history", CONF_HISTORY * max(0.0, decay))

  if not candidates:
    return {"value": None, "source": "none", "confidence": 0.0, "total": total,
            "candidates": (), "note": "noSource"}

  best = max(candidates, key=lambda c: (c["confidence"], c["value"]))
  note = "ok"

  # A two-lane jump needs strong evidence, otherwise keep the previous value.
  if history and isinstance(history.get("value"), int):
    previous = int(history["value"])
    if abs(best["value"] - previous) >= 2 and best["confidence"] < CONF_STRONG:
      held = [c for c in candidates if c["value"] == previous]
      if held:
        best = max(held, key=lambda c: c["confidence"])
        note = "holdHistory"

  return {"value": best["value"], "source": best["source"], "confidence": best["confidence"],
          "total": total, "candidates": tuple(candidates), "note": note,
          "junctionLanes": junction_lanes, "totalSource": total_source}
