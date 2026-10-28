# Independent CP navigation candidate — source foundation

User decision 2026-10-28: CP is independent from TesNav and may retain CP's
slow-lead passing/return behavior. This supersedes the previous CP passing
exclusion. Stereo speed measurement remains excluded.

## Status

This directory is deliberately **not an installable store plugin yet**: it has
no plugin.json, no running process and no vehicle hooks. It is a tested source
foundation for the independent plugin, not a deployed or road-validated release.
Existing TesNav/navassist and the running devices are unchanged.

Implemented locally:

- Original Carrot navigation kernel pinned to jixiexiaoge/carrot commit
  3615bf4bf40016f102e7d4af3745455a3791faa2. Native methods retain their ASTs;
  provenance.json records hashes. MIT notice is in CARROT-LICENSE.
- Explicit CP-only parameter and private message adapters. Legacy UDP/system-time
  mutation and live native publishers are excluded. No fake GPS CAN or invented
  phone heading. Fresh source, route, actual vehicle authority and driver vetoes
  are checked separately from native decisions.
- Bounded speed-target candidate, with opt-in increases, driver-setpoint cancel,
  route binding and absolute ceilings. This is a candidate, not a wired planner.
- CP passing state/threshold adaptation referencing navipilot latest-snapshot
  91d77de4fd7650ebc76c38cf4b47ede503f6d0dc AutoOvertakeManager.kt. It preserves
  normal slow-lead selection, driving-style multipliers, TBT direction bias,
  three new frames, 2.5s preparation, action cooldown, original-lane memory and
  a continuously qualified return interval. It is **not the complete original
  Kotlin manager** and does not execute on a vehicle.
- Completion requires actual start/finish/off observations. Queuing an intent
  never records completion. Unknown side/gap/crossing evidence blocks requests;
  factory BSM not-triggered alone is not proof of rear clearance.
- Carrot turn/fork intent adapter keeps a fork lamp in preparation through a
  crossing veto and prevents repeat requests after an observed completion.

## Required work before a release

1. Standalone manifest, BOOL master, CP-only settings/Chinese labels, entry hooks,
   process lifecycle, network binding and truthful telemetry capabilities.
2. Connect the native Carrot pipeline to the original CP v2 ingress; whitelist
   only effective CP-scoped remote settings and source-bound explicit commands.
3. Supply real qualified passing observations and retain original CP behavior
   that is not represented here (including early-trigger and side-lead/return
   assessment). Missing standard-host fields must remain unavailable.
4. Wire targets to every supported planner, including TN, and verify disable,
   fault and ownership paths. Preserve Panda and SP limits.
5. Mutual-exclusion UI/profile updates, full host/store gates, original-client
   interoperation, packaged candidate. Source gates do not establish firmware
   compilation, device activation, camera/model inference or road correctness.

No APK rebuild, device access, install, restart, parameter change, firmware
migration or road test has been performed for this candidate.

## Scoped local checks

```sh
PYTHONPATH=../xpilot:../xpilot/msgq_repo:../xpilot/opendbc_repo:plugins python3 -m pytest -q plugins/cp_nav/tests
```

23 cases passed on 2026-10-28. Failure checks were added and observed failing
before their corresponding changes. Full store release gates are pending until
the independent entry and production inputs exist.
