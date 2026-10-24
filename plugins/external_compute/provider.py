"""External compute provider interface. A provider moves ExternalData dicts between the device and one kind of
external compute; externald runs every provider in PROVIDERS and bridges them to cereal externalIn/externalOut.

Message dict (same fields as cereal ExternalData): source, kind, seq, payload (JSON text), validForMs.
Add a provider (e.g. an HTTP client for an LLM API): subclass Provider in its own module and list it in externald.
"""


class Provider:
  NAME = ""

  def poll(self, timeout: float) -> list[dict]:
    """Wait up to timeout seconds; return messages received from external compute."""
    return []

  def send(self, msg: dict) -> None:
    """Deliver one device message (from externalOut) to external compute, if this provider wants it."""

  def close(self) -> None:
    pass


def is_fresh(log_mono_ns: int, valid_for_ms: int, now_ns: int) -> bool:
  """Consumers: True while an externalIn message is within its validForMs (0 = no expiry)."""
  return valid_for_ms == 0 or 0 <= now_ns - log_mono_ns <= valid_for_ms * 1_000_000
