# Tesla map evidence: local validation, 2026-10-29

## Specifications and versions

Consulted upstream `onemiless/xpilot:xpilot` at
`b4181cebf62f90af44f4045e6a5d9735afe4264e`: AGENTS, XPILOT hard rules,
plugin/manifest APIs; store CONTRIBUTING at upstream
`92499491e34600f40b7f156b4686e45e803d9355`.
Paired local host: `b9dfad2f8fcf66119a444be52efd4b869616c0d1`.
Plugin source base: `af3b648bc971fc4c42a68d41ac0062159de5064d`, main.
No user WIP was present at task start; no branch switch or worktree creation.

Local API compatibility was checked directly. The local host uses `data_source`,
not upstream's newer computed `data` category; the new manifest uses the supported
local spelling. Only existing observe_can, publish_state and finite-TTL pluginMsg
interfaces are used. No host or firmware migration. Active-device versions were
not read: device access/deployment remains explicitly unauthorized for this task.

## Failure-first checks

The first contract run failed on missing map decoder/matcher. Integration checks
then reproduced actual old behavior: a sustained map conflict still emitted an
upward wheel tick, and navigation exposed no branch evidence. A separate check
reproduced stale fused input continuing to emit ticks. These cases passed after
implementation. Tests also cover bus aliasing, all 32 limit codes, branch SNA,
future/old timestamps, malformed frames, duplicate frames, route revisions,
both-sided forks, conditional limits, unit conversion, stale comparison and gaps.
An independent CANPacker assertion checks literal bits against the paired DBC.
Byte-identical passive decoder copies allow independent store installations.

## Source/local checks

- Focused map/navigation checks: 358 passed, Python 3.12.
- Full plugin regression: 834 passed, Python 3.12.
- Store E2E: local archives installed, discovered and enable/setting paths checked.
- Manifest compatibility and file layout: tesla_map, auto_speed, navassist passed.
- Independent switch checks, profile contract, CP candidate and nested-layout
  checks, Chinese metadata/glyph contract passed.
- Reproducible archives/index check and diff whitespace check passed.
- Runtime rule verifier: unchanged auto_speed/navassist compiled rule bytes match
  their reference bytes. The verifier release pin was advanced to auto_speed 1.2.0;
  rule, field, predicate, template, frequency and authorization checks remain intact.

## Artifacts and limits

Packaged tesla_map 1.0.0, auto_speed 1.2.0, navassist 2.1.0, zh_cn 1.1.10.
Their SHA-256 values are in index.json. No push was requested.

This changes map diagnostics, auto-speed conflict/freshness handling and quiet
navassist fork corroboration. Fork consistency is advisory, not unique junction
identity or permission; existing navigation direction, physical lamps, slowdown,
native SP/BSM/paint/edge/driver checks and GPIO rules remain unchanged.
No new GPS coordinate or absolute ego lane is inferred. No stereo/automatic
passing work was added. tn_long and cp_nav sources were not changed.

Firmware compilation: not performed. Runtime-rule byte generation is not firmware
compilation or a Panda execution test. Device installation/activation: not performed.
Real HUD rendering, actual CAN cadence/semantics and road accuracy: unverified.
A matching DBC/synthetic replay does not prove this vehicle broadcasts or implements
the signals as expected. No claim of completed vehicle validation is made.
