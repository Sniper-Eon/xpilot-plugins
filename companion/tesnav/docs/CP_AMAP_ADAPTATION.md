# TesNav-led AMap compatibility

Base: TesNav 19 / 1.7-xpilot-tesnav, plugin repository f1dd9cf.
Device reference: xpilot 7cf967f (2026-10-26), including DS's engagement fix,
parked settings access and Simplified Chinese translation. Do not replace these
with an older host. The reference is source inspection, not a new road validation.

Required failure cases, recorded before implementation:

- Legacy AMap send actions used by the CP companion never reach TesNav's receiver.
- Outbound AMap commands are mistaken for incoming navigation observations.
- Auto icons are interpreted as SDK icons, producing an incorrect next maneuver.
- Missing/invalid next-turn fields retain an instruction from the previous route.
- Optional camera fields are missing or malformed and invent a speed limit or crash.
- Destination arrival retains route identity, lanes or control eligibility.
- Camera/next-turn/status callbacks renew GPS, guidance timestamps or route identity.
- The adapter changes existing SDK navigation, explicit lane recommendations,
  single-camera vision, speech, or the reviewed v3 transport/freshness gates.
- An APK build is described as installation or actual C3 navigation acceptance.
- Fresh navigation text disappears only because vehicle localization is not ready;
  a display-only fix accidentally changes lane/control eligibility or keeps stale text.

Implementation uses the public CP companion's AMap broadcast field contracts as
reference (jixiexiaoge/navipilot, pinned public 3f1af5f, MIT), not the proprietary
CP 8.0.20 binary. Own adapter code retains TesNav's state and protocol. Preserve
the existing Auto 13012 lane parser and 60073 traffic-light parser; do not infer
control recommendations from display colors. No cloud key or model is extracted.

Candidate scope: standard/legacy send actions, next maneuver and distance from
10001, optional camera warnings, and explicit arrival 10019/39. Unknown lifecycle
codes remain inert; the public CP handler itself labels 10042 semantics as assumed.
Full map streaming to C3 is a separate capability and is not supplied here.

The C3 overlay may display fresh linked guidance when control localization is
unavailable, explicitly marked GUIDANCE ONLY. This changes presentation only;
runtime valid, lane readiness, source expiry and controller gates are unchanged.

Validation: run the new compatibility contracts before implementation, then all
Android unit tests and a signed tenengkai APK build. Actual phone installation,
real navigation, C3 source activation and road checks are separate receipts.

2026-10-26 result: signed APK 21 / 1.8-xpilot-amap built offline; Android tests
335 total, zero failures, one skipped. Plugin tests: 195 passed on Mac; the native
CAN-event contract that cannot load Mac's mismatched msgq binary passed separately
using the device's native runtime. The actual device host installer accepted the
1.3.0 candidate in an independent staging directory and discovered its manifest.
No process or control hook was started from that directory. The full Mac store E2E
also encounters that pre-existing msgq ABI mismatch; it is not reported as passed.

The user deferred phone work. APK installation, real AMap data acceptance, source
switching to TesNav (ExtNavAssistSource=0), active overlay rendering and road checks
remain pending. Keep active host 7cf967f and plugin 1.2.3 until the phone can be
connected and the vehicle is safely offroad. No firmware build/update is required
by these changes. An interrupted final staging refresh must be verified by hash
before the staged archive is used; the local dist/index are the delivery source.
