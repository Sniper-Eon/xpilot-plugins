"""Experimental extra veto before lane-change initiation; never grants clearance.

Configuration is an explicit file so a missing/invalid setup stays shadow. The
phone's observation-only packet stays control_eligible=False: only this
explicitly enabled local policy may consume it as an additional veto."""
from dataclasses import dataclass
import json
import math
from pathlib import Path

CONFIG_PATH = "/data/phone-vision/blindspot-assist.json"
OBSERVATION_PATH = "/dev/shm/phone_side_vehicles.json"
MAX_AGE_NS = 800_000_000
SOLID = 1
DASHED = 0


def bounded_json(path):
  with Path(path).open() as f:
    raw = f.read(16385)
  if len(raw) > 16384:
    raise ValueError("oversized")
  data = json.loads(raw)
  if not isinstance(data, dict):
    raise ValueError("not_object")
  return data


def load_mode(path=CONFIG_PATH):
  try:
    data = bounded_json(path)
    return "assist" if type(data.get("version")) is int and data["version"] == 1 and data.get("mode") == "assist" else "shadow"
  except (OSError, ValueError, TypeError, RecursionError, OverflowError):
    return "shadow"


@dataclass(frozen=True)
class PhoneSide:
  available: bool = False
  blocked: bool = False
  reason: str = "unavailable"


@dataclass(frozen=True)
class PhoneSideSpeed:
  """Nearest confirmed side vehicle. This is not a blind-spot occupancy decision."""
  available: bool = False
  distance_m: float | None = None
  relative_speed_mps: float | None = None
  absolute_speed_mps: float | None = None
  track_id: int | None = None
  track_hits: int | None = None
  track_confidence: float | None = None
  age_ms: int | None = None
  reason: str = "unavailable"


def _in_range(value, low, high):
  return type(value) in (int, float) and not isinstance(value, bool) and math.isfinite(value) and low <= float(value) <= high


def read_side_speeds(path=OBSERVATION_PATH, now_ns=None):
  """Per-side distance and speed from the phone, with the same freshness window as occupancy.

  Blind-spot blocking stays in PhoneBlindspotAssist.read and only looks at hits/confidence.
  """
  import time
  def blank(reason):
    return {"left": PhoneSideSpeed(reason=reason), "right": PhoneSideSpeed(reason=reason)}
  try:
    data = bounded_json(path)
  except (OSError, ValueError, TypeError, RecursionError, OverflowError):
    return blank("missing_or_malformed")
  if not isinstance(data, dict) or data.get("valid") is not True or data.get("control_eligible") is not False:
    return blank("invalid")
  if data.get("source") != "tesnav-phone" or type(data.get("version")) is not int or data["version"] != 1:
    return blank("invalid")
  stamp = data.get("updated_mono_ns")
  now = time.monotonic_ns() if now_ns is None else now_ns
  if type(stamp) is not int or not 0 <= now - stamp <= MAX_AGE_NS:
    return blank("stale")
  out = {}
  for side in ("left", "right"):
    value = data.get(side)
    if not isinstance(value, dict):
      out[side] = PhoneSideSpeed(reason="missing_side")
      continue
    age = value.get("age_ms")
    if age is not None and (type(age) is not int or not 0 <= age <= 500):
      out[side] = PhoneSideSpeed(reason="stale_measurement")
      continue
    hits = value.get("track_hits")
    if type(hits) is not int or not 3 <= hits <= 100000:
      out[side] = PhoneSideSpeed(reason="unconfirmed")
      continue
    distance = value.get("distance_m")
    relative = value.get("relative_speed_mps")
    absolute = value.get("absolute_speed_mps")
    distance_ok = _in_range(distance, 2, 100)
    relative_ok = _in_range(relative, -25, 25)
    absolute_ok = _in_range(absolute, 0, 70)
    if not (distance_ok or relative_ok or absolute_ok):
      out[side] = PhoneSideSpeed(reason="no_measurement")
      continue
    track = value.get("track_id")
    confidence = value.get("track_confidence")
    out[side] = PhoneSideSpeed(
      available=True,
      distance_m=float(distance) if distance_ok else None,
      relative_speed_mps=float(relative) if relative_ok else None,
      absolute_speed_mps=float(absolute) if absolute_ok else None,
      track_id=track if type(track) is int and track > 0 else None,
      track_hits=hits,
      track_confidence=float(confidence) if _in_range(confidence, 0, 1) else None,
      age_ms=age if type(age) is int else None,
      reason="ok",
    )
  return out


def lane_line_state(path=OBSERVATION_PATH, now_ns=None):
  """Solid/dashed verdict per side from the phone's lane-boundary classifier.

  Returns {} when the packet is missing, stale or malformed; a side with an unknown
  type is reported as None."""
  import time
  try:
    data = bounded_json(path)
  except (OSError, ValueError, TypeError, RecursionError, OverflowError):
    return {}
  if not isinstance(data, dict) or not data.get('valid'):
    return {}
  stamp = data.get('updated_mono_ns')
  now = time.monotonic_ns() if now_ns is None else now_ns
  if type(stamp) is not int or not 0 <= now - stamp <= MAX_AGE_NS:
    return {}
  line = data.get('lane_line')
  if not isinstance(line, dict):
    return {}
  out = {}
  for side in ('left', 'right'):
    value = line.get(side)
    out[side] = value if type(value) is int and value in (DASHED, SOLID) else None
  return out


class PhoneBlindspotAssist:
  def __init__(self, mode=None, path=OBSERVATION_PATH):
    self.mode = load_mode() if mode is None else mode
    self.path = path
    self.stream = None
    self.last_capture = -1
    self.empty = [0, 0]
    self.states = (PhoneSide(), PhoneSide())

  @property
  def enabled(self):
    return self.mode == "assist"

  def unknown(self, reason):
    self.empty = [0, 0]
    self.states = (PhoneSide(reason=reason), PhoneSide(reason=reason))
    return self.states

  # 每类道路的"算作有车"的置信度门限。越高越宽松（不容易拦），越低越保守。
  BLOCK_THRESHOLD_BY_KIND = {"expressway": 0.6, "urban_expressway": 0.6, "ramp": 0.45}

  def read(self, now_ns, road_kind="unknown"):
    try:
      data = bounded_json(self.path)
      stamp, stream = data.get("updated_mono_ns"), data.get("stream_id")
      if (type(data.get("version")) is not int or data["version"] != 1 or
          data.get("source") != "tesnav-phone" or data.get("valid") is not True or
          data.get("control_eligible") is not False or
          not isinstance(stream, str) or not 8 <= len(stream) <= 128 or
          type(stamp) is not int or not 0 <= now_ns - stamp <= MAX_AGE_NS):
        return self.unknown("invalid_or_stale")
      if stream != self.stream:
        if stamp <= self.last_capture:
          return self.unknown("old_stream")
        self.stream = stream
        self.empty = [0, 0]
        self.states = (PhoneSide(), PhoneSide())
      if stamp < self.last_capture:
        return self.unknown("out_of_order")
      if stamp == self.last_capture:
        return self.states
      if self.last_capture >= 0 and stamp - self.last_capture > MAX_AGE_NS:
        self.empty = [0, 0]
        self.states = (PhoneSide(), PhoneSide())
      self.last_capture = stamp
      states = []
      for i, side in enumerate(("left", "right")):
        if side not in data:
          self.empty[i] = 0
          states.append(PhoneSide(reason="missing_side"))
          continue
        value = data[side]
        if value is None:
          self.empty[i] += 1
          if self.empty[i] >= 3:
            states.append(PhoneSide(True, False, "no_confirmed_phone_target"))
          elif self.states[i].blocked:
            states.append(PhoneSide(True, True, "target_release_pending"))
          else:
            states.append(PhoneSide(reason="warming_up"))
          continue
        self.empty[i] = 0
        confidence = value.get("confidence") if isinstance(value, dict) else None
        hits = value.get("hits") if isinstance(value, dict) else None
        threshold = self.BLOCK_THRESHOLD_BY_KIND.get(str(road_kind), .30)
        if (type(confidence) in (int, float) and math.isfinite(confidence) and
            threshold <= confidence <= 1 and type(hits) is int and 3 <= hits <= 100000):
          states.append(PhoneSide(True, True, "confirmed_phone_target"))
        else:
          states.append(PhoneSide(reason="unconfirmed_or_malformed_target"))
      self.states = tuple(states)
      return self.states
    except (OSError, ValueError, TypeError, RecursionError, OverflowError):
      return self.unknown("missing_or_malformed")
