#!/usr/bin/env python3
"""Stage one X-Pilot profile in a NEW directory; never activates/restarts a device.

Failure contract: wrong host, mismatched archives, missing native binary, reuse of
an active folder, profile/phone-source conflict must fail or be explicitly deferred.
Existing Params, legacy checkout, firmware and launcher are never changed.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def prepare(host, profile, destination):
  host = host.resolve()
  destination = destination.resolve()
  d = json.loads((ROOT / "profiles" / f"xpilot-{profile}.json").read_text())
  if d["host"] != "Sniper-Eon/xpilot" or not (host / "XPILOT.md").is_file():
    raise ValueError("wrong host")
  subprocess.run(["git", "merge-base", "--is-ancestor", d["host_min_commit"], "HEAD"], cwd=host, check=True)
  if destination.exists():
    raise ValueError("destination must be new; active folders are never reused")
  # Set isolation before importing host modules. No compiled Params needed.
  os.environ["XPILOT_PLUGINS_DIR"] = str(destination)
  sys.path[:0] = [str(host), str(host / "opendbc_repo"), str(host / "msgq_repo")]
  from openpilot.tesla import store, manifest

  entries = {e["id"]: e for e in json.loads((ROOT / "index.json").read_text())["plugins"]}
  planned = []
  deferred = []
  for pid in d["plugins"]:
    if pid not in entries:
      if (ROOT / "plugins" / pid / "build_native.py").is_file():
        deferred.append(pid)
        continue
      raise ValueError("missing plugin " + pid)
    e = entries[pid]
    if not manifest.platform_ok(e.get("platform")):
      deferred.append(pid)
      continue
    archive = ROOT / "dist" / f"{pid}-{e['version']}.tar.gz"
    if hashlib.sha256(archive.read_bytes()).hexdigest() != e["sha256"]:
      raise ValueError("hash mismatch " + pid)
    planned.append((e, archive))
  destination.mkdir(parents=True)
  for e, archive in planned:
    entry = store.IndexEntry(
      **{k: e[k] for k in ("id", "name", "version", "api", "category", "author", "description", "sha256", "platform")},
      url=archive.as_uri(),
      installable=True,
    )
    error = store.install(entry)
    if error:
      raise ValueError(e["id"] + ": " + error)
  loaded, errors = manifest.load_all(destination)
  if errors:
    raise ValueError(str(errors))
  params = destination / ".params"
  params.mkdir(exist_ok=True)
  for key, value in d["params"].items():
    (params / key).write_text(value)
  receipt = {
    "profile": d["id"],
    "host_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=host, text=True).strip(),
    "installed": [m.id for m in loaded],
    "deferred_native_build": deferred,
    "source": d["source"],
    "activated": False,
    "road_validated": False,
    "destination": str(destination),
  }
  (destination / ".profile.json").write_text(json.dumps(receipt, indent=2) + "\n")
  return receipt


if __name__ == "__main__":
  p = argparse.ArgumentParser(description=__doc__)
  p.add_argument("--host", type=Path, required=True)
  p.add_argument("--profile", choices=["cpdazi", "tesnav"], required=True)
  p.add_argument("--destination", type=Path, required=True)
  a = p.parse_args()
  print(json.dumps(prepare(a.host, a.profile, a.destination), indent=2))
