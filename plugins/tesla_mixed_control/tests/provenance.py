"""Export committed test inputs without Git history; verify every exported byte.

The manifest records provenance from a trusted local exporter, not a signature.
It must travel through the same reviewed channel as the source archive.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

PREFIX = "plugins/tesla_mixed_control"
FIXTURE = "plugins/conftest.py"
MANIFEST = "tesla-mixed-source.json"
CACHES = {"__pycache__", ".pytest_cache"}


def git(repo, *args):
  return subprocess.check_output(["git", "-C", str(repo), *args])


def files(plugin):
  root = plugin.parents[1]
  paths = []
  for path in plugin.rglob("*"):
    if CACHES & set(path.relative_to(plugin).parts):
      continue
    if path.is_symlink():
      raise ValueError(f"source links not allowed: {path}")
    if path.is_file():
      paths.append(path)
  fixture = root / FIXTURE
  if fixture.is_symlink() or not fixture.is_file():
    raise ValueError("missing or linked test fixture")
  paths.append(fixture)
  return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def source(plugin, manifest=None):
  plugin = plugin.resolve()
  hashes = files(plugin)
  if manifest is None:
    repo = Path(git(plugin, "rev-parse", "--show-toplevel").decode().strip()).resolve()
    if plugin != repo / PREFIX or not git(repo, "ls-files", "--", PREFIX).strip():
      raise ValueError("plugin is not tracked at the expected Git repository path")
    return {"kind": "git", "commit": git(repo, "rev-parse", "HEAD").decode().strip(),
            "dirty": bool(git(repo, "status", "--porcelain", "--", PREFIX, FIXTURE).strip()), "sha256": hashes}
  manifest = Path(manifest).resolve()
  data = json.loads(manifest.read_text(encoding="utf-8"))
  if (manifest.parent / PREFIX).resolve() != plugin:
    raise ValueError("source manifest must be beside its exported plugins directory")
  if data.get("schema") != 1 or not re.fullmatch(r"[0-9a-f]{40}", str(data.get("commit", ""))):
    raise ValueError("invalid source provenance schema or immutable Git commit")
  if data.get("sha256") != hashes:
    raise ValueError("exported source differs from manifest (missing, added or changed file)")
  return {"kind": "verified_archive", "commit": data["commit"], "sha256": hashes,
          "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest()}


def export(repo, revision, output):
  commit = git(repo, "rev-parse", "--verify", f"{revision}^{{commit}}").decode().strip()
  entries = git(repo, "ls-tree", "-rz", commit, "--", PREFIX, FIXTURE).split(b"\0")
  blobs = {}
  for entry in filter(None, entries):
    meta, raw_path = entry.split(b"\t", 1)
    mode, kind, oid = meta.decode().split()
    path = raw_path.decode("utf-8")
    if mode not in ("100644", "100755") or kind != "blob":
      raise ValueError(f"only ordinary committed files can be exported: {path}")
    if path != FIXTURE and not path.startswith(PREFIX + "/"):
      raise ValueError(f"unexpected export path: {path}")
    blobs[path] = git(repo, "cat-file", "blob", oid)
  if FIXTURE not in blobs or not any(p.startswith(PREFIX + "/") for p in blobs):
    raise ValueError("commit does not contain plugin and shared test fixture")
  output.mkdir(parents=True, exist_ok=False)
  for name, content in blobs.items():
    target = output / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
  record = {"schema": 1, "commit": commit,
            "sha256": {p: hashlib.sha256(content).hexdigest() for p, content in sorted(blobs.items())}}
  manifest = output / MANIFEST
  manifest.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
  return source(output / PREFIX, manifest)


if __name__ == "__main__":
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--repo", type=Path, required=True)
  parser.add_argument("--revision", default="HEAD")
  parser.add_argument("--export", type=Path, required=True)
  args = parser.parse_args()
  print(json.dumps(export(args.repo, args.revision, args.export), indent=2))
