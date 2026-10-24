#!/usr/bin/env python3
"""externald: bridges external compute providers to cereal. Provider messages -> externalIn; externalOut -> providers.
Providers come from the active plugins' external_provider hooks. A provider that raises is closed and dropped; the others keep running."""
from openpilot.cereal import messaging
from openpilot.common.params import Params
from openpilot.common.swaglog import cloudlog
from openpilot.tesla import plugins

FIELDS = ("source", "kind", "seq", "payload", "validForMs")


def main() -> None:
  providers = plugins.external_providers(Params())
  pm = messaging.PubMaster(["externalIn"])
  out_sock = messaging.sub_sock("externalOut", conflate=False)

  while providers:
    for p in list(providers):
      try:
        for m in p.poll(0.02):
          msg = messaging.new_message("externalIn")
          for k in FIELDS:
            setattr(msg.externalIn, k, m[k])
          pm.send("externalIn", msg)
        for event in messaging.drain_sock(out_sock):
          out = {k: getattr(event.externalOut, k) for k in FIELDS}
          for q in providers:
            q.send(out)
      except Exception:
        cloudlog.exception(f"external provider {p.NAME} failed, closed")
        providers.remove(p)
        p.close()


if __name__ == "__main__":
  main()
