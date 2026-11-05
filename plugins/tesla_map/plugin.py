"""Tesla map data as an xpilot card plugin: decode 0x238 ``UI_driverAssistMapData`` (vehicle bus) and publish a small
snapshot for the tile. Read-only: no claims, no CAN sends, no control output.

The snapshot goes to the plugin param ``ExtTeslaMapState`` (JSON) at most twice a second and only when it changed. The
tile in ``ui.py`` polls the same key, so the card process stays the only reader of the CAN stream.
"""
from __future__ import annotations

import logging
import time

from opendbc.car.tesla.values import CANBUS
from openpilot.tesla.plugin import Plugin

from .compare import LimitComparator
from .decode import MAP_ADDRESS, MapData, decode_frame, is_fresh
from .view import build_payload

STATE_PARAM = "ExtTeslaMapState"
WRITE_INTERVAL_NS = 500_000_000
LOG = logging.getLogger(__name__)


class TeslaMap(Plugin):
  """Keeps the newest vehicle-bus map frame and publishes the snapshot the tile reads."""

  def __init__(self, CP, params):
    super().__init__(CP, params)
    self.params = params
    self.data: MapData | None = None
    self.received_ns = 0
    self.comparator = LimitComparator()
    self._last_write_ns = 0
    self._last_payload: dict | None = None
    self._write_failed = False

  def _now_ns(self) -> int:
    return time.monotonic_ns()

  def observe_can(self, can_list, now_ns: int) -> list:
    for mono_time, frames in can_list:
      for address, data, source in frames:
        # 0x238 also exists on the autopilot-party bus as STW_ACTN_RQ (right scroll wheel); only source 1 is map data.
        if address != MAP_ADDRESS or source != CANBUS.vehicle:
          continue
        decoded = decode_frame(data)
        if decoded is not None:
          self.data, self.received_ns = decoded, mono_time
    return []

  def publish_state(self, CS_SP) -> None:
    now = self._now_ns()
    data = self.data if self.data is not None and is_fresh(self.received_ns, now) else None
    sp_mps = float(CS_SP.speedLimit) if CS_SP is not None else 0.0
    comparison = self.comparator.update(data.speed_limit if data is not None else None,
                                        data.unit if data is not None else "kph", sp_mps, now,
                                        trusted=bool(data is not None and data.regular and data.gps_match))
    if now - self._last_write_ns < WRITE_INTERVAL_NS:
      return
    payload = build_payload(data, comparison, sp_mps)
    if payload == self._last_payload:
      return
    try:
      self.params.put(STATE_PARAM, payload)
    except Exception:
      # A params failure must not drop the plugin: the tile simply keeps the previous snapshot.
      if not self._write_failed:
        self._write_failed = True
        LOG.warning("tesla_map: cannot publish %s", STATE_PARAM, exc_info=True)
      return
    self._write_failed = False
    self._last_payload, self._last_write_ns = payload, now
