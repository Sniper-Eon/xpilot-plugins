"""Read-only diagnostics for the HOLD_ROAD recording build.

Nothing returned here is consumed by planning, signalling or actuation.
"""
from __future__ import annotations


ACTION_BITS = {
  "straight": 1 << 0,
  "left": 1 << 1,
  "right": 1 << 2,
  "uturn_left": 1 << 3,
  "uturn_right": 1 << 4,
}


def expected_action(maneuver):
  m = str(maneuver or "").lower()
  if m == "straight": return "straight"
  if m in ("slight_left", "turn_left", "sharp_left", "exit_left", "ramp_left"): return "left"
  if m in ("slight_right", "turn_right", "sharp_right", "exit_right", "ramp_right"): return "right"
  if m == "u_turn_left": return "uturn_left"
  if m == "u_turn_right": return "uturn_right"
  return None


def observe(nav, previous_key=None):
  step = nav.get("currentStepIndex", -1)
  link = nav.get("currentLinkIndex", -1)
  point = nav.get("currentPointIndex", -1)
  key = (step, link) if isinstance(step, int) and step >= 0 and isinstance(link, int) and link >= 0 else None
  action = expected_action(nav.get("maneuver"))
  recommended = [lane for lane in (nav.get("lanes") or ()) if lane.get("recommended") is True]
  if not action:
    status = "unchecked"
  elif not recommended:
    status = "none"
  else:
    bit = ACTION_BITS[action]
    matches = sum(bool(int(lane.get("allowedActions") or 0) & bit) for lane in recommended)
    status = "match" if matches == len(recommended) else ("partial" if matches else "conflict")
  return {
    "step": step, "link": link, "point": point, "roadKey": key,
    "linkChanged": bool(key is not None and previous_key is not None and key != previous_key),
    "maneuver": nav.get("maneuver"), "recommendationAction": status,
    "laneCount": len(nav.get("lanes") or ()),
  }
