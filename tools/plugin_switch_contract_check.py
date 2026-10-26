#!/usr/bin/env python3
"""Before implementation: missing/shared/non-BOOL switches must fail; integrated navigation must pass."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

TOOL = Path(__file__).with_name('plugin_switch_contract.py')


def manifest(pid, key, kind='BOOL'):
  return dict(id=pid, enable_param=key, params={key: dict(type=kind, default='0')} if key else {})


def main():
  cases = [
    ('independent', [manifest('navassist', 'Nav'), manifest('vision', 'Vision')], True),
    ('integrated-navigation', [dict(manifest('navassist', 'Nav'), settings=[
      dict(key='Lane', label='Lane'), dict(key='Signal', label='Signal')])], True),
    ('missing-switch', [manifest('bad', None)], False),
    ('shared-switch', [manifest('first', 'Shared'), manifest('second', 'Shared')], False),
    ('non-bool', [manifest('bad', 'Bad', 'INT')], False),
    ('undeclared', [dict(id='bad', enable_param='Bad', params={})], False),
    ('directory-mismatch', [manifest('wrong', 'Wrong')], False),
  ]
  for label, docs, expected in cases:
    with tempfile.TemporaryDirectory() as raw:
      root = Path(raw)
      for doc in docs:
        folder = 'other' if label == 'directory-mismatch' else doc['id']
        target = root / 'plugins' / folder
        target.mkdir(parents=True)
        (target / 'plugin.json').write_text(json.dumps(doc))
      result = subprocess.run([sys.executable, str(TOOL), '--root', str(root)], capture_output=True, text=True)
      assert (result.returncode == 0) == expected, (label, result.stdout, result.stderr)
  print(json.dumps(dict(cases=len(cases), passed=True)))


if __name__ == '__main__':
  main()
