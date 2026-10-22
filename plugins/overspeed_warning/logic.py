"""Pure decision logic (no openpilot imports), so it can be checked anywhere."""
KPH = 3.6


def overspeed_kph(v_ego: float, limit: float, margin_kph: float) -> int | None:
  """km/h over (limit + margin), or None. limit <= 0 means no known limit."""
  if limit <= 0.0:
    return None
  over = (v_ego - limit) * KPH
  return round(over) if over > margin_kph else None
