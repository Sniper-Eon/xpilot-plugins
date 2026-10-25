"""Fresh, named-producer state only; an expired message clears the display."""

KINDS = {'nav': 'nav.state', 'intent': 'lanes.intent', 'oem': 'oem.lanes', 'topology': 'lanes.topology'}


def read_state(messages):
  result = {}
  for field, kind in KINDS.items():
    value = messages.fresh(kind).get('navassist')
    result[field] = value if isinstance(value, dict) else {}
  return result
