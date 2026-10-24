"""External compute bridge over real localhost sockets.

- E1 lines from a client that has not sent a valid hello are published
- E2 a wrong token keeps the connection open
- E3 an authenticated client's messages are not published, or lose kind/payload/validForMs/source
- E4 an oversize line is buffered without limit instead of dropping the client
- E5 malformed JSON or a non-object line crashes the bridge
- E6 outbound messages reach unauthenticated clients, or miss authenticated ones
- E7 more than max_clients connections are accepted
- E8 a client flooding faster than max_rate_hz gets every message through
- E9 a client disconnecting mid-stream crashes the bridge
- E10 is_fresh accepts an expired message, or rejects one with validForMs 0 (no expiry)
"""
import json
import socket
import time

from ..provider import is_fresh
from ..tcp import TcpProvider

TOKEN = "s3cret"


def connect(port: int) -> socket.socket:
  s = socket.create_connection(("127.0.0.1", port), timeout=2)
  s.settimeout(0.5)
  return s


def line(s: socket.socket, obj) -> None:
  s.sendall(obj if isinstance(obj, bytes) else json.dumps(obj).encode() + b"\n")


def drain(p: TcpProvider, seconds: float = 0.3) -> list[dict]:
  out, end = [], time.monotonic() + seconds
  while time.monotonic() < end:
    out += p.poll(0.05)
  return out


def recv_lines(s: socket.socket) -> list[dict]:
  data = b""
  try:
    while chunk := s.recv(65536):
      data += chunk
  except (TimeoutError, socket.timeout):
    pass
  return [json.loads(x) for x in data.splitlines() if x.strip()]


def closed(s: socket.socket) -> bool:
  try:
    return s.recv(1) == b""
  except (TimeoutError, socket.timeout):
    return False
  except OSError:
    return True


def test_bridge_e1_to_e9():
  # One sequence: each step relies on the connections and state left by the previous ones.
  errors = []
  p = TcpProvider(TOKEN, host="127.0.0.1", port=0, max_clients=3, max_line=1024, max_rate_hz=20)
  try:
    anon = connect(p.port)
    line(anon, {"kind": "x", "payload": 1})
    if drain(p):
      errors.append("E1 unauthenticated message published")

    bad = connect(p.port)
    line(bad, {"hello": "wrong", "name": "bad"})
    drain(p)
    if not closed(bad):
      errors.append("E2 wrong token left open")

    good = connect(p.port)
    line(good, {"hello": TOKEN, "name": "laptop"})
    drain(p)
    if recv_lines(good) != [{"ok": True}]:
      errors.append("E3 no hello ack")
    line(good, {"kind": "llm.reply", "payload": {"text": "hi"}, "validForMs": 500, "seq": 7})
    got = drain(p)
    want = {"source": "laptop", "kind": "llm.reply", "payload": json.dumps({"text": "hi"}), "validForMs": 500, "seq": 7}
    if len(got) != 1 or any(got[0].get(k) != v for k, v in want.items()):
      errors.append(f"E3 got {got}")

    line(good, b"{not json}\n")
    line(good, b"[1, 2]\n")
    try:
      if drain(p):
        errors.append("E5 malformed line published")
    except Exception as e:
      errors.append(f"E5 bridge raised {e!r}")

    p.send({"kind": "llm.ask", "payload": json.dumps({"q": "why"})})
    if [m.get("kind") for m in recv_lines(good)] != ["llm.ask"]:
      errors.append("E6 authenticated client missed outbound")
    if recv_lines(anon):
      errors.append("E6 unauthenticated client got outbound")

    extra = [connect(p.port) for _ in range(3)]
    drain(p)
    if not any(closed(s) for s in extra):
      errors.append("E7 more than max_clients accepted")

    for i in range(100):
      line(good, {"kind": "flood", "payload": i})
    n = len(drain(p, 0.5))
    if n >= 100:
      errors.append(f"E8 flood not limited ({n}/100)")

    big = connect(p.port) if not closed(anon) else None
    line(good, b"x" * 5000)
    drain(p)
    if not closed(good):
      errors.append("E4 oversize line did not drop the client")

    anon.close()
    try:
      drain(p)
    except Exception as e:
      errors.append(f"E9 disconnect raised {e!r}")
    if big:
      big.close()
  finally:
    p.close()
  assert errors == []


def test_is_fresh_e10():
  now = 10_000_000_000
  assert not is_fresh(now - 600_000_000, 500, now)
  assert is_fresh(now - 400_000_000, 500, now)
  assert is_fresh(0, 0, now)
