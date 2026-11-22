"""1 Hz side-vehicle speed logger for offline accuracy checks. Never affects control.

Appends one JSON line per second to /data/navassist_logs/side_speed_YYYYmmdd.log
(day in UTC+8). Stops writing once the directory holds more than CAP_BYTES; it
never deletes anything. Every error is swallowed so navassist cannot break.
"""
import json
import os
import time

from .phone import OBSERVATION_PATH, bounded_json, read_side_speeds

LOG_DIR = "/data/navassist_logs"
CAP_BYTES = 200 * 1024 * 1024
TZ_OFFSET_S = 8 * 3600
_state = {"next": 0.0, "next_cap": 0.0, "capped": False}


def _r(v, n=2):
  try:
    return None if v is None else round(float(v), n)
  except (TypeError, ValueError):
    return None


def _lead(model):
  try:
    leads = list(getattr(model, "leadsV3", []) or [])
    if not leads:
      return None
    lead = leads[0]
    return dict(prob=_r(getattr(lead, "prob", None)), x=_r(getattr(lead, "x", None)), v=_r(getattr(lead, "v", None)))
  except Exception:
    return None


def _dir_bytes(path):
  total = 0
  for name in os.listdir(path):
    try:
      total += os.path.getsize(os.path.join(path, name))
    except OSError:
      pass
  return total


def build_line(now_ns, cs, model, phone_sides, wall_s=None, obs_path=OBSERVATION_PATH):
  wall_s = time.time() if wall_s is None else wall_s
  local = time.gmtime(wall_s + TZ_OFFSET_S)
  speeds = read_side_speeds(obs_path, now_ns)
  try:
    raw = bounded_json(obs_path)
  except Exception:
    raw = {}
  out = dict(
    t=time.strftime("%Y-%m-%dT%H:%M:%S", local) + "+08:00",
    wall_ms=int(wall_s * 1000),
    v_ego=_r(getattr(cs, "vEgo", None)),
    car_bsm_l=bool(getattr(cs, "leftBlindspot", False)),
    car_bsm_r=bool(getattr(cs, "rightBlindspot", False)),
    obs_age_ms=None,
    model_lead=_lead(model),
  )
  stamp = raw.get("updated_mono_ns") if isinstance(raw, dict) else None
  if type(stamp) is int:
    out["obs_age_ms"] = (now_ns - stamp) // 1_000_000
  for i, side in enumerate(("left", "right")):
    s = speeds.get(side)
    rv = raw.get(side) if isinstance(raw, dict) else None
    rv = rv if isinstance(rv, dict) else {}
    ps = phone_sides[i] if phone_sides else None
    out[side] = dict(
      ok=bool(s and s.available), reason=getattr(s, "reason", None),
      distance_m=_r(getattr(s, "distance_m", None)),
      relative_speed_mps=_r(getattr(s, "relative_speed_mps", None)),
      absolute_speed_mps=_r(getattr(s, "absolute_speed_mps", None)),
      track_id=getattr(s, "track_id", None), track_hits=getattr(s, "track_hits", None),
      track_confidence=_r(getattr(s, "track_confidence", None), 3), age_ms=getattr(s, "age_ms", None),
      bs_occupied=(None if ps is None else bool(ps.blocked)),
      bs_reason=(None if ps is None else ps.reason),
      bs_hits=rv.get("hits"), bs_confidence=_r(rv.get("confidence"), 3),
    )
  return out


def tick(now_ns, cs, model, phone_sides, offroad=False):
  try:
    mono = time.monotonic()
    if mono < _state["next"]:
      return
    _state["next"] = mono + 1.0
    if offroad:
      return
    os.makedirs(LOG_DIR, exist_ok=True)
    if mono >= _state["next_cap"]:
      _state["next_cap"] = mono + 60.0
      _state["capped"] = _dir_bytes(LOG_DIR) > CAP_BYTES
    if _state["capped"]:
      return
    line = build_line(now_ns, cs, model, phone_sides)
    day = line["t"][:10].replace("-", "")
    with open(os.path.join(LOG_DIR, "side_speed_%s.log" % day), "a") as f:
      f.write(json.dumps(line, ensure_ascii=False, separators=(",", ":")) + "\n")
  except Exception:
    pass
