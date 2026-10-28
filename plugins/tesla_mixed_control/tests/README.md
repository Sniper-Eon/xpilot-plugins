# Test source provenance

Normal checkout tests record the Git commit, scoped dirty state and file hashes.
Source-only exports are supported without copying Git history or inventing Git metadata.
Commit the intended test changes first, then export only this plugin and its shared
`plugins/conftest.py` fixture from actual Git blobs:

```sh
python3 plugins/tesla_mixed_control/tests/provenance.py \
  --repo . --revision HEAD --export /tmp/mixed-source
```

The destination must not exist. The exporter ignores working-tree modifications,
preserves committed bytes, and writes `tesla-mixed-source.json` with the full commit
SHA and SHA256 of every exported file. This manifest is trusted local provenance,
not a signed attestation: transfer it with the reviewed source using the same trusted
channel, and record the transfer archive hash. Do not generate it from arbitrary files
on the target and claim that those files came from the recorded commit.

On the target, keep the manifest beside the exported `plugins` directory. Set the
normal host dependency paths, then explicitly select it:

```sh
export TESLA_MIXED_SOURCE_MANIFEST=/tmp/mixed-source/tesla-mixed-source.json
python3 -m pytest -q /tmp/mixed-source/plugins/tesla_mixed_control/tests/test_e2e.py
```

Before executing the control sequence, the E2E requires an exact file inventory and
hash match, including the shared fixture. Missing, altered or extra source files and
symlinks fail validation; Python/pytest caches are excluded. A bare export without a
manifest still fails. `source.json` distinguishes `verified_archive` from `git` and
records the manifest hash. The host must still be a Git checkout and retains its own
commit record. No host or plugin runtime behavior changes.

The provenance regression can run without host dependencies:

```sh
python3 plugins/tesla_mixed_control/tests/test_provenance.py
```

These helpers and this document live under `tests/`, which the official store builder
excludes from plugin archives. This test-only change does not replace published packages.
