# xpilot-plugins

Plugin repository for [xpilot](https://github.com/onemiless/openpilot/tree/xpilot) (Tesla-only sunnypilot fork).
Devices list this repository under Settings → Plugins → Plugin Store, install while parked, and apply on restart.

插件仓库：xpilot 设备在 设置 → Plugins → Plugin Store 里浏览这里的插件，停车时安装，重启后生效。
接口、类别、资源声明和底线规则见 xpilot 仓库根目录的 `XPILOT.md`。

## Layout

```
plugins/<id>/            plugin source: __init__.py, plugin.json (manifest), plugin.py, optional ui.py and modules
dist/<id>-<ver>.tar.gz   reproducible archives, generated
index.json               what devices read: id, version, api, category, url, sha256, generated
tools/build_index.py     builds dist/ and index.json; --check verifies they are current
```

## Submitting a plugin / 提交插件

1. Fork, add `plugins/<id>/`, open a pull request. Read `XPILOT.md` first.
2. `plugin.json`: `id` equals the directory, `api` is the host's API version (1), a category from `XPILOT.md`,
   `claims` for everything the plugin uses, params with types BOOL/INT/FLOAT/STRING/JSON. Downloaded plugins
   must not reuse built-in ids or param keys; prefix keys with `Ext`.
3. Use relative imports inside the plugin (`from .logic import x`): installed plugins load as `xpilot_ext.<id>`.
4. Pure Python only. Compiled code (acados solvers, C extensions) and panda safety plugins cannot be installed
   from the store.
5. Run `python3 tools/build_index.py` and commit `dist/` and `index.json` with the source.
6. Describe in the PR what the plugin changes on the road, which claims it takes, and how you tested it.

## Review checklist (maintainer) / 审核清单

- `python3 tools/build_index.py --check` passes on the PR head (archives match the reviewed source).
- From an xpilot checkout: `python3 tools/sp_tesla_e2e/store_e2e.py --repo <this checkout>` passes.
- Claims match the code: every CAN address sent, hook used and process started is claimed; nothing reads
  or writes outside its own params and messages; no network access unless it is an external compute provider.
- Control plugins (lateral, longitudinal, lane change, engagement, ...) state their floors and failure behaviour.
- No obfuscated code, no downloaded or generated code at runtime, no subprocess or shell use.

Archives are not signed yet: the sha256 in `index.json` only protects against corrupt or swapped downloads.
Trust comes from this reviewed repository, so only merge what you have read.

## Example

`plugins/overspeed_warning`: alerts category, one store-backed setting, an `alert` claim and a relative import.
