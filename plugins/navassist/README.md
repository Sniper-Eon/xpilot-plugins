# Navigation Assist 1.2

Personal fork: [Sniper-Eon/xpilot](https://github.com/Sniper-Eon/xpilot), branch `xpilot`.
Install this plugin only with the paired host containing `openpilot/tesla/lane_policy.py` and the
`navassist` panda safety plugin. API 1 alone does not identify that capability.

## Migrated behavior

- Existing phone v3 UDP 4213, signed HTTP 7766, signed discovery 7765 and parked-only pairing.
- Strict packet/replay/TTL handling, `routeAvoid`, request-sequence ACK and display-only lane feedback.
- Navigation lane preparation retains the signal while a confirmed OEM boundary/BSM veto prevents SP starting
  or continuing a lane change. The generic host context can only restrict SP; it cannot initiate steering.
- Same-adjacent absolute/relative source changes preserve the request, reset readiness and require fresh
  observations. Missing observations and recovery confirmation have separate bounded timers.
- Turn-only lamps do not become lane-change requests; lane-position lamps do not generate a turn desire.
- Three distinct fresh model frames plus a physical right carriageway anchor are required for absolute lane
  numbering. Merely matching the visible and map lane counts is insufficient. Ambiguous geometry is unknown.
- Navigation-only chime on SP's observed lane-change start, once per request. Manual changes stay silent.
- Maneuver speed ceilings only lower the target; missing control context, poor GPS or stale guidance rejects it.
- Optional phone blind spot **extra veto**, off by default. Missing phone data never proves clearance.
- Stereo, closing-speed experiments and proactive passing have been removed.

The process reuses `modelV2` geometry. It opens no camera, converts no images and runs no neural network.
Geometry cannot identify painted solid lines: OEM rejection is used when available. The legacy explicitly
permitted unknown-paint fallback remains limited by SP's road-edge, blind-spot, speed, lateral and panda gates.
This is not proof that an unobserved boundary is safe.

## Plugin interfaces and settings

`pluginMsg`: `nav.state`, `lanes.topology`, `lanes.intent`, `oem.lanes`.
Only messages from producer `navassist` are consumed. Expired displays clear; an expired owned lamp cannot
fall through into automatic lane-change permission. Explicit disable clears coordinators immediately.

All configuration lives in the store's private parameter directory, not new core Params keys.
The master, lane positioning, physical lamp and phone-veto switches default off. Pairing identities are private;
reset is accepted only offroad. Existing keys/codes must be migrated privately during installation.
Diagnostics rotate under the device data directory; driving logs and keys are excluded from this repository.

The separate `phone_vision` plugin provides single wide-camera frames for the companion app.
It is disabled by default and not started by navigation. Dual camera, overtaking and external model control
have been removed. External model control is not supplied by this navigation plugin.

## Physical lamps and firmware

Card clones a fresh idle 0x3E9 bus-1 template. Only request/reason/counter/checksum change. Driver opposite
signals/hazards take priority without a cancellation injection. The panda safety plugin checks the template,
checksum, controls_allowed for active requests, bus, size, 100 ms rate, and 200 frames per 60 seconds.
Cancel is permitted without controls_allowed because it only releases an owned lamp.
SP and Tesla remain the lane-change/steering authorities. Host checks, native safety tests, actual firmware
compilation, device build, parked validation and road validation are separate evidence.

## Validation

From `plugins/`, with the paired xpilot checkout on PYTHONPATH:

```
python3 -m pytest -q navassist/tests phone_vision/tests
```

Run `tools/sp_tesla_e2e/store_e2e.py --repo ../xpilot-plugins` in the system checkout for archive installation,
discovery and host checks. `migration-source.json` identifies the legacy coordinator source. A successful
local check does not mean this version has been installed or road-tested.

## Two X-Pilot profiles

`ExtNavAssistSource` is read once at process startup: 0 = existing TesNav v3; 1 = CPdazi8 v2.
Only the chosen transport opens sockets; there is no source fallback or simultaneous command stream.
CP uses port7714 `/api/navi/ws/v2/control/amap_auto_1.0` and bound JSON streams,
UDP7705 discovery, and read-only7000 `/api/heartbeat_status` and `/ws/compact_state`.
The CP compatibility layer is independent code based on observed protocol fields, not copied app controllers.
It subscribes only to JSON; native BSM/vehicle metadata needs no camera images.

CP compatibility is currently partial and candidate-only. Only fresh native `carState` is returned in compact
telemetry. Missing model/radar/Carrot-specific services stay unavailable; CP-only car fields are reserved padding
listed in heartbeat capabilities. A missing side radar track never means an empty safe lane.
Remote Params, CP model downloads, CP cloud authorization, destination injection and passing commands are
unsupported. The original CP app may still show its own unsupported controls. No entitlement is bypassed.
CP navigation observations expire independently of reception/heartbeat. Stale/absent GPS, route, guidance
or status cannot start a request. A new control lease resets the source. Fresh native localization and normal
SP/Tesla gates are still required by the shared coordinator. Real CP app interoperability is pending.
