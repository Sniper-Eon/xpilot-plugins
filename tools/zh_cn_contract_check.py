#!/usr/bin/env python3
"""Before implementation: translate names, descriptions and choice labels; preserve raw values and unknown text."""
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
  path = ROOT / 'plugins/zh_cn/catalog.py'
  spec = importlib.util.spec_from_file_location('zh_catalog_contract', path)
  module = importlib.util.module_from_spec(spec)
  sys.modules[spec.name] = module
  spec.loader.exec_module(module)
  translator = module.ChineseCatalog()
  checked = 0
  for p in (ROOT / 'plugins').glob('*/plugin.json'):
    d = json.loads(p.read_text())
    fields = [d['name'], d.get('description', '')]
    for row in d.get('settings', []):
      fields.append(row['label'])
      fields.extend(str(label) for label, _ in row.get('choices', []))
    for text in fields:
      if text and any(c.isalpha() for c in text):
        result = translator.translate(text)
        assert isinstance(result, str) and any('\u4e00' <= c <= '\u9fff' for c in result), (p.parent.name, text)
        checked += 1
  for text in ('ExtNavAssistEnabled', '0x3E9', '192.168.5.182', 'keep_right', 'MyPrivateWifi'):
    assert translator.translate(text) is None, text
  assert translator.translate('Eco') == '\u7ecf\u6d4e'
  assert translator.translate('Normal') == '\u6807\u51c6'
  assert translator.translate('Sport') == '\u8fd0\u52a8'
  assert '1.3.0' in translator.translate('v1.3.0 - Sniper-Eon - Navigation lane positioning')
  assert translator.translate('8 s') == '8 \u79d2'
  assert translator.translate('TURN R  35 m') == '\u53f3\u8f6c  35 \u7c73'
  assert set(''.join(translator.strings.values())).issubset(set(translator.glyphs))
  assert translator.font_path.is_file() and translator.font_path.stat().st_size > 1_000_000
  print(json.dumps(dict(passed=True, translated_metadata_fields=checked)))


if __name__ == '__main__':
  main()
