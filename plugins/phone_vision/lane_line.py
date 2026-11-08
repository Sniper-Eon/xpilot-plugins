"""Lane-boundary paint classification reported by the phone (0 dashed, 1 solid).

The phone's LaneLineDetector is a live observation over the visible corridor: it never
proves that a boundary is legally crossable, so this module only feeds an extra veto.
"""
import math


def validate(value):
  if value is None:
    return None
  if not isinstance(value, dict):
    raise ValueError('invalid_lane_line_observation')
  left, right = value.get('left'), value.get('right')
  if type(left) is not int or type(right) is not int or not 0 <= left <= 1 or not 0 <= right <= 1:
    raise ValueError('invalid_lane_line_types')
  out = {'left': left, 'right': right}
  for key in ('left_conf', 'right_conf'):
    conf = value.get(key)
    if type(conf) in (int, float) and math.isfinite(conf) and 0 <= conf <= 1:
      out[key] = float(conf)
  return out
