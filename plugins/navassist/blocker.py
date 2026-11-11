"""Sticky per-side lane-change veto with two-frame confirmation.

The plugin has no solid/dashed classifier of its own, so the reliable evidence is Tesla's factory ALC verdict
(oem.lanes) plus the phone blindspot report. A single frame never vetoes; a confirmed veto clears only after
clear_frames frames without it."""
from __future__ import annotations


class LaneChangeBlocker:
  def __init__(self, *, clear_frames: int = 6, confirm_frames: int = 2):
    if clear_frames <= 0 or confirm_frames <= 0:
      raise ValueError("frame counts must be positive")
    self.clear_frames = clear_frames
    self.confirm_frames = confirm_frames
    self._remaining = [0, 0]
    self._streak = [0, 0]
    self._reason = ["", ""]
    self._last_evidence = None

  def reset(self) -> None:
    self._remaining = [0, 0]
    self._streak = [0, 0]
    self._reason = ["", ""]
    self._last_evidence = None

  def update(self, oem: dict | None, topology: dict | None, *,
             phone_left: bool = False, phone_right: bool = False,
             car_left: bool = False, car_right: bool = False,
             paint_left: bool = False, paint_right: bool = False,
             ignore_paint: bool = False) -> tuple[bool, bool, tuple[str, str]]:
    oem = oem or {}
    topology_valid = bool((topology or {}).get("valid"))
    evidence = (oem.get('alcStampNs'), oem.get('mapStampNs')) if 'alcStampNs' in oem else None
    new_evidence = evidence is None or evidence != self._last_evidence
    self._last_evidence = evidence
    # Explicit OEM/map reject always vetoes. The "availability" verdict may be speed/map gated, so it only
    # vetoes when local topology cannot confirm a crossing.
    # IGNORE_PAINT_AT_JUNCTION：路口前转弯本来就要跨过左/右实线，实线不构成拦截理由。
    paint_left = bool(paint_left) and not ignore_paint
    paint_right = bool(paint_right) and not ignore_paint
    sources = [
      ('oemExplicit' if oem.get("leftExplicitBlock") else 'oemAvailability'
       if (oem.get("leftAvailabilityBlock") and not topology_valid) else 'phoneBlindspot' if phone_left
       else 'bsmObject' if car_left else 'paintSolid' if paint_left else ''),
      ('oemExplicit' if oem.get("rightExplicitBlock") else 'oemAvailability'
       if (oem.get("rightAvailabilityBlock") and not topology_valid) else 'phoneBlindspot' if phone_right
       else 'bsmObject' if car_right else 'paintSolid' if paint_right else ''),
    ]
    immediate = [bool(sources[0]), bool(sources[1])]
    reasons = []
    for side, detected in enumerate(immediate):
      if not detected:
        self._streak[side] = 0
      elif ((phone_left if side == 0 else phone_right) or (car_left if side == 0 else car_right)
            or (paint_left if side == 0 else paint_right)):
        self._streak[side] = self.confirm_frames  # 手机多帧确认或车辆 CAN 盲区，均视为已确认
      elif new_evidence:
        self._streak[side] += 1
      confirmed = self._streak[side] >= self.confirm_frames
      if confirmed:
        self._remaining[side] = self.clear_frames
        reasons.append(sources[side] or "unknown")
      elif self._remaining[side] > 0:
        self._remaining[side] -= 1
        reasons.append(self._reason[side])
      else:
        reasons.append("")
      if confirmed:
        self._reason[side] = reasons[-1]
      elif self._remaining[side] == 0:
        self._reason[side] = ""
    blocked = (self._remaining[0] > 0, self._remaining[1] > 0)
    return blocked[0], blocked[1], (self._reason[0], self._reason[1])
