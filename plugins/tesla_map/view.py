"""Card-to-UI snapshot (Params JSON) and the tile text. Stdlib only so tests run without pyray.

The card plugin publishes the dict from build_payload(); the tile polls the same key and renders tile_lines(). Keeping
both here means one tested definition of what the car sends and what the screen shows.
"""
from __future__ import annotations

from .compare import AGREE, MAP_HIGHER, MAP_LOWER, MAP_ONLY, SP_ONLY, Comparison
from .decode import MapData

SCHEMA = 1
ADVISORY_SUFFIX = {"ADVISORY": " ADV", "DEPENDENT": " DEP", "BUMPS": " BUMP"}


def build_payload(data: MapData | None, comparison: Comparison, sp_mps: float) -> dict:
  """Compact, JSON-serialisable snapshot. ``fresh`` False means the last 0x238 frame is missing or stale."""
  limit = None
  road = None
  nav = None
  reject = None
  dep = None
  misc = None
  if data is not None:
    limit = {
      "code": data.speed_code, "value": data.speed_limit, "unit": data.unit, "type": data.limit_type,
      "unlimited": data.unlimited, "regular": data.regular,
    }
    road = {
      "class": data.road_class, "label": data.road_label, "controlled": data.controlled_access,
      "gps": data.gps_match, "country": data.country_code, "streets": data.street_count,
    }
    nav = {
      "active": data.nav_active, "branch_m": data.branch_distance_m, "side": data.branch_side,
      "left_ramp": data.branch_left_ramp, "right_ramp": data.branch_right_ramp,
    }
    reject = {
      "left": data.reject_left, "right": data.reject_right, "left_free": data.reject_left_free,
      "right_free": data.reject_right_free, "autosteer": data.reject_autosteer,
      "hands_on": data.reject_hands_on, "nav": data.reject_nav, "hpp": data.reject_hpp,
    }
    dep = {"code": data.dependency, "label": data.dependency_label}
    misc = {
      "supercharger": data.supercharger, "botts": data.accept_botts, "as_restricted": data.autosteer_restricted,
      "pmm": data.pmm, "sca": data.sca, "park_parallel": data.parallel_autopark,
      "park_perp": data.perpendicular_autopark,
    }
  return {
    "v": SCHEMA,
    "fresh": data is not None,
    "sp_mps": round(float(sp_mps), 3) if sp_mps and sp_mps > 0.0 else 0.0,
    "limit": limit,
    "road": road,
    "nav": nav,
    "reject": reject,
    "dep": dep,
    "misc": misc,
    "cmp": {"state": comparison.state, "map": comparison.map_value, "sp": comparison.sp_value,
            "delta": comparison.delta, "conflict": comparison.conflict},
  }


def _limit_line(limit: dict, conflict: bool) -> str:
  if limit.get("unlimited"):
    text = "MAP UNL"
  elif limit.get("value") is None:
    text = "MAP --"
  else:
    text = f"MAP {int(limit['value'])}"
  text += ADVISORY_SUFFIX.get(str(limit.get("type")), "")
  return text + " !" if conflict else text


def _context_line(road: dict, nav: dict) -> str:
  label = str(road.get("label") or "")
  road_text = f"HWY {label}" if road.get("controlled") else ("" if label in ("", "SNA") else label)
  if not nav.get("active"):
    return road_text
  branch_m = nav.get("branch_m")
  if branch_m is None:
    nav_text = "NAV"
  else:
    side = str(nav.get("side") or "")
    nav_text = "EXIT NOW" if branch_m == 0 else f"EXIT {int(branch_m)}"
    nav_text += f" {side}" if side else ""
  return f"{road_text} {nav_text}".strip()


def _compare_line(cmp: dict, unlimited: bool = False) -> str:
  state, sp, delta = cmp.get("state"), cmp.get("sp"), cmp.get("delta")
  if state == AGREE:
    return f"SP {sp} OK"
  if state in (MAP_HIGHER, MAP_LOWER) and delta is not None:
    return f"SP {sp} {int(delta):+d}"
  if state == MAP_ONLY:
    return "MAP ONLY"
  if state == SP_ONLY:
    # "MAP UNL" is map data, not missing map data: drop the NO MAP suffix.
    return f"SP {sp}" if unlimited else f"SP {sp} NO MAP"
  return ""


def _reject_line(reject: dict) -> str:
  labels = [name for key, name in (("left", "L"), ("right", "R"), ("left_free", "LF"), ("right_free", "RF"),
                                   ("autosteer", "AS"), ("hands_on", "HO")) if reject.get(key)]
  return "REJ " + " ".join(labels) if labels else ""


def tile_lines(payload: dict | None) -> tuple[str, ...]:
  """Up to four ASCII lines for the tile; the host drops the ones that do not fit, so order is priority."""
  if not isinstance(payload, dict) or not payload.get("fresh"):
    return ("MAP SNA",)
  limit, road, nav = payload.get("limit") or {}, payload.get("road") or {}, payload.get("nav") or {}
  cmp = payload.get("cmp") or {}
  lines = [
    _limit_line(limit, bool(cmp.get("conflict"))),
    _context_line(road, nav),
    _compare_line(cmp, bool(limit.get("unlimited"))),
    _reject_line(payload.get("reject") or {}),
  ]
  return tuple(line for line in lines if line)
