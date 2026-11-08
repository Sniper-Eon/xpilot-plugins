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
  def _norm(v):
    # 手机用 -1 表示「这一侧没识别出来」：按未知处理，不因此拒绝整帧。
    if type(v) is not int:
      raise ValueError('invalid_lane_line_types')
    return v if v in (0, 1) else None
  left, right = _norm(value.get('left')), _norm(value.get('right'))
  if left is None and right is None:
    return None
  out = {}
  if left is not None:
    out['left'] = left
  if right is not None:
    out['right'] = right
  for key in ('left_conf', 'right_conf'):
    conf = value.get(key)
    if type(conf) in (int, float) and math.isfinite(conf) and 0 <= conf <= 1:
      out[key] = float(conf)
  return out
