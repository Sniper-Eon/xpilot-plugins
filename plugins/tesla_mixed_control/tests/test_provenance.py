"""Archive evidence must reject altered, missing and extra source, and absent metadata.

Run with unittest directly: no compiled host dependencies are needed for this gate.
"""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("mixed_provenance", Path(__file__).with_name("provenance.py"))
provenance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(provenance)


class ArchiveProvenanceTest(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    self.addCleanup(self.tmp.cleanup)
    self.repo = Path(self.tmp.name) / "repo"
    self.repo.mkdir()
    self.plugin = self.repo / "plugins/tesla_mixed_control"
    self.plugin.mkdir(parents=True)
    (self.plugin / "plugin.py").write_bytes(b"VALUE = 1\n")
    (self.repo / "plugins/conftest.py").write_bytes(b"# fixture\n")
    self.git("init", "-q")
    self.git("add", ".")
    self.git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture")
    self.sha = self.git("rev-parse", "HEAD").strip()
    self.output = Path(self.tmp.name) / "export"
    provenance.export(self.repo, self.sha, self.output)
    self.exported = self.output / "plugins/tesla_mixed_control"
    self.manifest = self.output / provenance.MANIFEST

  def git(self, *args):
    return subprocess.check_output(["git", "-C", str(self.repo), *args], text=True)

  def test_export_uses_commit_not_dirty_checkout(self):
    clean = provenance.source(self.plugin)
    self.assertEqual(clean["kind"], "git")
    self.assertEqual(clean["commit"], self.sha)
    self.assertFalse(clean["dirty"])
    (self.plugin / "plugin.py").write_text("DIRTY = True\n")
    self.assertTrue(provenance.source(self.plugin)["dirty"])
    other = Path(self.tmp.name) / "other"
    provenance.export(self.repo, self.sha, other)
    self.assertEqual((other / "plugins/tesla_mixed_control/plugin.py").read_bytes(), b"VALUE = 1\n")
    info = provenance.source(self.exported, self.manifest)
    self.assertEqual(info["commit"], self.sha)
    self.assertEqual(info["kind"], "verified_archive")
    self.assertFalse((self.output / ".git").exists())
    # Reproduces the old E2E failure without executing unrelated control tests.
    self.assertNotEqual(subprocess.run(["git", "-C", str(self.exported), "rev-parse", "HEAD"],
                                      capture_output=True).returncode, 0)

  def test_tampered_or_missing_file_rejected(self):
    file = self.exported / "plugin.py"
    file.write_text("VALUE = 9\n")
    with self.assertRaises(ValueError):
      provenance.source(self.exported, self.manifest)
    file.unlink()
    with self.assertRaises(ValueError):
      provenance.source(self.exported, self.manifest)

  def test_extra_file_and_changed_fixture_rejected(self):
    extra = self.exported / "extra.py"
    extra.write_text("pass\n")
    with self.assertRaises(ValueError):
      provenance.source(self.exported, self.manifest)
    extra.unlink()
    (self.output / "plugins/conftest.py").write_text("# changed\n")
    with self.assertRaises(ValueError):
      provenance.source(self.exported, self.manifest)

  def test_missing_metadata_or_wrong_commit_rejected(self):
    with self.assertRaises((ValueError, subprocess.CalledProcessError)):
      provenance.source(self.exported)
    data = json.loads(self.manifest.read_text())
    data["commit"] = "HEAD"
    self.manifest.write_text(json.dumps(data))
    with self.assertRaises(ValueError):
      provenance.source(self.exported, self.manifest)


if __name__ == "__main__":
  unittest.main()
