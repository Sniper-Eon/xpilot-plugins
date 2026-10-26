# xpilot-plugins

Plugin repository for [xpilot](https://github.com/Sniper-Eon/xpilot) (Tesla-only sunnypilot fork).
Devices list this repository under Settings → Plugins → Plugin Store, install while parked, and apply on restart.

插件仓库：xpilot 设备在 设置 → Plugins → Plugin Store 里浏览这里的插件，停车时安装，重启后生效。
接口、类别、资源声明和底线规则见 xpilot 仓库根目录的 `XPILOT.md`。

2026-10-26 用户确认：可选车辆功能通过各自插件的独立总开关启用；**导航相关功能继续
集成在一个 navassist 插件**，内部保留变道、打灯、降速和提示音设置，不拆成多个导航插件。
源码核查、开关清单与边界见 [插件架构核查](docs/PLUGIN_ARCHITECTURE_AUDIT_20261026.md)。

## Layout

```
plugins/<id>/            plugin source: __init__.py, plugin.json (manifest), plugin.py, optional ui.py and modules
dist/<id>-<ver>.tar.gz   reproducible archives, generated
index.json               what devices read: id, version, api, category, url, sha256, generated
tools/build_index.py     builds dist/ and index.json; --check verifies they are current
```

## Submitting a plugin / 提交插件

1. Fork, add `plugins/<id>/`, open a pull request (see `CONTRIBUTING.md`). Read `XPILOT.md` first.
2. `plugin.json`: `id` equals the directory, `api` is the host's API version (1), a category from `XPILOT.md`,
   `claims` for everything the plugin uses, params with types BOOL/INT/FLOAT/STRING/JSON. Downloaded plugins
   must not reuse built-in ids or param keys; prefix new keys with `Ext`. The plugins moved here from the xpilot
   repository keep their original key names so existing device settings stay valid.
3. Use relative imports inside the plugin (`from .logic import x`): installed plugins load as `xpilot_ext.<id>`.
4. Prefer pure Python. Compiled code must ship as prebuilt binaries with a `platform` and a `build_native.py`
   that reproduces them (see Native plugins). panda safety code is compiled into the firmware and lives in the
   xpilot repository (`opendbc/safety/plugins/safety.json`). A plugin with `can.tx` claims or a `safety` block
   installs only if both match that file exactly on the device's xpilot version.
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

## Plugins

- `plugins/overspeed_warning`: example. Alerts category, one store-backed setting, an `alert` claim, a relative import.
- `plugins/tn_long`: TN longitudinal (TN-NoDEC) as a `long_planner`, with prebuilt acados solvers. See its README.
- `plugins/navassist`: phone navigation ingest, maneuver speed ceiling, OEM lane-change veto and a bounded physical
turn signal on 0x3E9. See its README; the panda side is `navassist` in the system repository's `safety.json`.
- `plugins/zh_cn`: optional Simplified Chinese UI, including option values and descriptions; requires the paired
  host's generic UI translation hook. Own master switch, no vehicle hooks or parameter writes.

Moved from the xpilot repository (keep their original param keys):

- Display, installed by default on first boot: `speed_card`, `lead_card`, `speed_limit_card`, `car_tile`, `map_tile`,
  `clock_tile`, `ip_tile`, `blindspot_edges`.
- `bms`: battery tile. `traffic_light`: traffic light stop/start. `external_compute`: external compute bridge.
- Safety-backed (need the matching panda firmware entry): `auto_speed` (0x3C2), `ambient_light` (0x679).

Tests: `cd plugins && python3 -m pytest -q .` with an xpilot checkout on `PYTHONPATH` (see `.github/workflows/ci.yml`).

## Native plugins / 带二进制的插件

Plugins with compiled code ship prebuilt binaries for one platform: `plugin.json` gets
`"platform": {"machine": "aarch64", "python": "cpython-312"}` (written by the plugin's `build_native.py`, run on the
target device). Devices only offer and load a native plugin on a matching platform. Binaries cannot be reviewed like
source: review the build script, and rebuild them yourself on your device before merging.

## 两个 X-Pilot 候选配置

见 [TWO_VARIANTS.md](TWO_VARIANTS.md) 和 `profiles/`：CP搭子版、特会开版均使用
Sniper-Eon/xpilot 的 xpilot 分支，插件基础相同，仅导航来源独占选择不同。
双目测距/测速、自动超车与自动回原车道已从本项目当前应用和服务中移除。
两版初始为导航观察模式，物理打灯、导航变道和取图关闭；不是已完成路测的安装版。
CP版目前支持导航v2接收和原车盲区状态回传，尚未完成真实CP App联调，其他CP专有接口见兼容清单。
原有单目手机识别代码保留为可选功能，开启前仍须完成取图负载验证。
