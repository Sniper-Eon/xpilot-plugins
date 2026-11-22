"""Approach-window helper for display / v3 remap / fusion.

The numbers MUST stay identical to planning.py RECOMMENDATION_GATE
(250 m regular / 800 m expressway / 640 m urban expressway, and
TURN_PREPARE_M = 400 m for left/right/U-turn). Planning itself is
not imported and is not modified.

Gaode's lane list is the layout of the upcoming intersection segment,
not the car's current position. Paths that number or display lanes
should hold the current-road layout until this window, then switch
to the intersection numbering.
"""
from __future__ import annotations

import math

ROAD_KIND_LOOKAHEAD_SCALE = {"expressway": 1.0, "urban_expressway": 0.8, "ramp": 0.0}
TURN_PREPARE_MANEUVERS = frozenset((
    "turn_left", "turn_right", "u_turn_left", "u_turn_right",
    "turnLeft", "sharpLeft", "uTurnLeft",
    "turnRight", "sharpRight", "uTurnRight",
))
TURN_PREPARE_M = 400.0
_DIRECTIONAL_PREFIXES = (
    "turn_", "slight_", "keep_", "ramp_", "exit", "fork", "merge",
    "u_turn", "uturn", "roundabout", "turnL", "turnR", "sharp", "uTurn",
)


def rec_gate_m(road_kind=None, maneuver=None) -> float:
    kind = str(road_kind or "unknown")
    man = str(maneuver or "none")
    scale = ROAD_KIND_LOOKAHEAD_SCALE.get(kind, 1.0)
    gate = (800.0 * scale if kind in ("expressway", "urban_expressway") else 250.0)
    if man in TURN_PREPARE_MANEUVERS:
        gate = max(gate, TURN_PREPARE_M)
    return gate


def in_approach_window(distance_m, road_kind=None, maneuver=None) -> bool:
    try:
        d = float(distance_m)
    except (TypeError, ValueError):
        return False
    if not math.isfinite(d) or d <= 0.0:
        return False
    return d <= rec_gate_m(road_kind, maneuver)


def is_directional_maneuver(maneuver) -> bool:
    man = str(maneuver or "none")
    if man in ("none", "unknown", "destination", "", "straight"):
        return False
    if man in TURN_PREPARE_MANEUVERS:
        return True
    return man.startswith(_DIRECTIONAL_PREFIXES)


def is_current_road_layout(n, rec, road_total, distance_m, road_kind=None, maneuver=None) -> bool:
    """True if this Amap lane list should be treated as the current road, not the upcoming intersection."""
    if not isinstance(n, int) or n < 2:
        return False
    rec_set = {int(i) for i in (rec or ()) if isinstance(i, int)}
    all_rec = (not rec_set) or (len(rec_set) >= n)
    approaching = in_approach_window(distance_m, road_kind, maneuver)
    directional = is_directional_maneuver(maneuver)
    if approaching:
        return road_total is not None and n == road_total
    if road_total is not None and n == road_total:
        return True
    if road_total is not None and n != road_total:
        # A jumped count while a maneuver is active is the intersection list arriving early.
        if directional:
            return False
        return all_rec
    if directional and not all_rec:
        return False
    return True
