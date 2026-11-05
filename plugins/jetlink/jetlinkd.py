"""Plugin-owned Jetlink gadget owner.

Runs the vendored jetlink.comma.owner against the plugin's own params store and the plugin adapter.
The big-model attach is still disabled; this step only brings up the owner/provisioning path.
"""
from __future__ import annotations

import sys
from pathlib import Path

VENDOR = Path(__file__).resolve().parent / 'vendor'
if str(VENDOR) not in sys.path:
  sys.path.insert(0, str(VENDOR))

from jetlink.openpilot.interface import Keys, OwnerConfig  # noqa: E402
from jetlink.openpilot.owner import main as owner_main  # noqa: E402

PLUGIN = Path(__file__).resolve().parent

CHESTNUT_IDS = frozenset({(0xADD1, 0x0001), (0xADD1, 0x0002), (0x3801, 0x0001), (0x174C, 0x2464), (0x174C, 0x2463)})
PARAMS = Path('/data/xpilot_plugins/.params')
LOG = Path('/data/xpilot_plugins/jetlink/jetlinkd.log')


def main() -> int:
  keys = Keys(link='ExtJetlinkLink', offroad='ExtJetlinkOffroad', progress='ExtJetlinkProgress',
              spec='ExtJetlinkSpec', pointers='ExtJetlinkPointers', big_model='ExtJetlinkBigModel', catalog=None)
  env = {'PYTHONPATH': f'{VENDOR}:{PLUGIN / "pylib"}:/data/openpilot'}
  config = OwnerConfig(params_dir=PARAMS, keys=keys, chestnut_ids=CHESTNUT_IDS,
                       adapter='jetlink_plugin_adapter', cwd=Path('/data/openpilot'),
                       env=env, log_file=LOG)
  owner_main(config)
  return 0


if __name__ == '__main__':
  raise SystemExit(main())
