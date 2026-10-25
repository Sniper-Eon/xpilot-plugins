"""Bounded read-only phone observation reader, shared by runtime diagnostics."""
import json
from pathlib import Path


def read_packet(path=Path('/dev/shm/phone_side_vehicles.json')):
  try:
    with path.open() as stream:
      raw = stream.read(16385)
    return json.loads(raw) if len(raw) <= 16384 else None
  except (OSError, ValueError, RecursionError):
    return None
