"""Fresh, named-producer state only; an expired message clears the display."""

KINDS = {'nav': 'nav.state', 'intent': 'lanes.intent', 'oem': 'oem.lanes', 'topology': 'lanes.topology'}


def guidance_visible(nav):
  """Fresh route text is useful even when localization forbids vehicle assistance."""
  return bool(nav.get('valid') or (nav.get('linked') and not nav.get('stale', True)
    and nav.get('routeActive') and nav.get('mode') == 'realtime'
    and nav.get('maneuver') not in (None, '', 'none', 'unknown')))


def guidance_only(nav):
  return guidance_visible(nav) and not nav.get('valid', False)


def read_state(messages):
  result = {}
  for field, kind in KINDS.items():
    value = messages.fresh(kind).get('navassist')
    result[field] = value if isinstance(value, dict) else {}
  return result
