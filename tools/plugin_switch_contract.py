#!/usr/bin/env python3
"""Check store-plugin master-switch metadata; runtime disable behaviour needs separate validation."""
import argparse
import json
from pathlib import Path


def check(root):
  errors, switches = [], {}
  paths = sorted((root / 'plugins').glob('*/plugin.json'))
  if not paths:
    errors.append('No store plugin manifests found')
  for path in paths:
    name = path.parent.name
    try:
      doc = json.loads(path.read_text())
      if not isinstance(doc, dict):
        raise ValueError('manifest must be an object')
      if doc.get('id') != name:
        errors.append(f'{name}: manifest id must match its directory')
      key = doc.get('enable_param')
      if not isinstance(key, str) or not key.isidentifier():
        errors.append(f'{name}: store plugin needs its own named master switch')
        continue
      params = doc.get('params', {})
      spec = params.get(key) if isinstance(params, dict) else None
      if not isinstance(spec, dict) or spec.get('type') != 'BOOL':
        errors.append(f'{name}: {key} must be a BOOL declared in this plugin')
      if key in switches:
        errors.append(f'{name}: master switch {key} is shared with {switches[key]}')
      else:
        switches[key] = name
    except (OSError, ValueError) as exc:
      errors.append(f'{name}: {exc}')
  return dict(plugin_count=len(paths), unique_master_switches=len(switches), errors=errors)


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
  result = check(parser.parse_args().root)
  print(json.dumps(result, indent=2))
  return bool(result['errors'])


if __name__ == '__main__':
  raise SystemExit(main())
