# Personal fork migration, 2026-10-25

System: [Sniper-Eon/xpilot, xpilot](https://github.com/Sniper-Eon/xpilot/tree/xpilot).
Store and phone source: this repository, `main`.
These are candidate sources. The running legacy C3 has not been replaced by this migration.
The user authorized deployment after validation; actual device build, OS/hardware checks and parked
runtime validation remain required before activation.

| Existing capability | New location | Migration status |
|---|---|---|
| Phone navigation / UDP ACK / routeAvoid | `plugins/navassist` | Migrated, local protocol/socket checks passed |
| Signed discovery and HTTP / parked pairing | `plugins/navassist` | Migrated, private identities require private device transfer |
| Recommended lane preparation / continuity fix | `plugins/navassist` + generic host lane context | Migrated, local actual-DesireHelper checks passed |
| OEM solid-boundary / blind-spot veto | `plugins/navassist` | Keeps preparation lamps; never grants clearance from a veto |
| Navigation-only start chime | `plugins/navassist` | Migrated, manual lane changes excluded |
| Absolute lane numbering | model geometry + physical right-edge anchor | Conservative replacement; no extra image classifier; ambiguous is unknown |
| Navigation display / maneuver speed ceiling | `plugins/navassist` | Migrated, expiry/control-context checks passed |
| Phone side-car inference / connection code | `plugins/phone_vision` + `companion/tesnav` | Single wide-camera transport; master OFF; device load check pending |
| Front-visible closing-risk observation | `plugins/navassist/closing.py` | Diagnostic only; speed accuracy not established here |
| Auto speed, traffic light, BMS, lighting, UI tiles | Existing independent store plugins | Retained from xpilot store; installed/discovered locally |
| Dual camera / metric stereo experiments | Phone source retained | OFF; no successful runtime/accuracy claim |
| Mac external large-model driving backend | Existing external-compute advice plugin only | Not a port of Jetlink modeld; no activation |
| Automatic overtaking / Tesla body camera | No activation | Not enabled; body-camera integration was cancelled |

Local evidence:

- 538 plugin tests passed, including legacy coordinator/protocol and new migration contracts.
- 16 host/generated/store/fork checks passed; 17 packaged plugins installed and discovered without load errors.
- Android: 344 JVM tests, zero failures/errors, one skip; signed candidate APK v18 built with the original
  package/certificate. See `companion/tesnav/BUILD-VALIDATION.json`. iOS source retained, not rebuilt.
- Native panda safety: 34 tests passed, 110 subtests, six inventory skips; UBSan enabled. Mac needed a locally
  ad-hoc-signed copy of the compiler sanitizer runtime for its Python loader. No safety logic was weakened.
- F4 and H7 Panda firmware compiled, not flashed. Safety MISRA scan with cppcheck 2.22.0 returned zero.
- Full C3 native build, UI rendering, active camera load, device activation and road validation: pending.

Do not transfer driving logs, captured images, pairing secrets, API keys or signing credentials into Git.
Keep old device checkout/Params and firmware recovery material before any activation. AGNOS 19.9 and the
correct C3-specific boot-chain manifest must be checked; this source migration does not authorize an
unreviewed OS image update. Phone capture and dual-camera experiments stay off during the platform switch.
