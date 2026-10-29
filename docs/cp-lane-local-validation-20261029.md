# CP phone lane interface: local candidate, 2026-10-29

## Scope and versions

User requested CP lane-model reuse in navassist, permitted APK edits, explicitly
limited work to local validation and prohibited deployment. No SSH/ADB/device
settings/restarts/installs were performed for this task.

Plugin source base: 4a8f5d2 (main). Paired local host remains
b9dfad2f8fcf66119a444be52efd4b869616c0d1. The last deployment record also names
that host with 4a8f5d2 plugin changes; devices were not queried this turn.
Existing JSON settings, phone observation, process, HUD and message interfaces
suffice; no new host hooks/firmware ABI or cereal fields are needed.

Consulted upstream onemiless/xpilot:xpilot AGENTS, XPILOT hard rules and
plugin/manifest definitions, plus onemiless/xpilot-plugins:main CONTRIBUTING.
Content SHA256 values observed:

- AGENTS: a54bc2083c3145263fb8d36b7eac620202a5aa8b554963d2546885758aaef043
- XPILOT: 644f988fc67ef1bb525f4fe46f4106055e92981fed5dc59f33ce7b541f797fe4
- plugin.py: 411ce75d1b22fa6902471567cfb37cd883c173f6c78e1961d7c05bf07063305b
- manifest.py: d5b8d11ab4bffd433d819198d8d848d064fd5cd123c4f2ebad5097d554517064
- CONTRIBUTING: f7c37b870e704f82c8710e7c827366bd69f7d8f095c1d3a95e6d8996dbbf24b2

## Reference and implementation

CP APK SHA256 c107503712f8938a4663824cda9366caefea4548c66df9809b4483976f0ceeae.
Static APK inspection found LaneNative.nativeInferCompact on decoded I420 Y
planes, an empty optional scratch buffer, eight class scores, day/night MNN
models and liblanenet binding MNN from libVAE. This is distinct from route
recommendations and CP's JSON lane_current stream. The reference APK and public
CP source are not assumed to be the same revision or share all asset licenses.

The independent JNI declaration preserves the required class ABI but does not
change the TesNav package/signature. Libraries and models are extracted only to
an explicit private directory outside this repository, then optionally included
in the tenengkai build. They are not committed, downloaded or published.

Native runtime is in a non-exported separate process; the client has bounded
single-flight requests, timeouts and no late-result reuse. Existing wide JPEG
transport is reused with RGB-to-Y conversion, which is not identical to CP's
original WebRTC path. Phone and navassist opt-ins default off. Three consistent
fresh original frames produce a visible-corridor estimate; only agreement with
already-qualified geometric position changes the HUD to corroborated. Geometry
remains the only existing source of absolute position; recommendations, model
classes, BSM absence and missing data never grant lane clearance. No lamps,
actuation, stereo speed or automatic passing logic changed.

## Failure-first and local results

Initial checks failed because navassist lacked phone lane evidence, transport
discarded lane_cp, and native isolation was absent. A later regression reproduced
a timestamp relabel refreshing a repeated frame; it now rejects that case.
Checks cover route reset, stale/absent/disabled data, frame identity, ordering,
invalid numbers, forbidden control permission and transport-to-HUD replay.

- Full plugin regression: 839 passed.
- Android Debug JVM tests: 350 total, 349 passed, 1 existing skipped test.
- Signed tenengkai APK v28 assembled successfully, package/signature match v27.
- ELF architecture and five JNI exports verified; bundled model/library hashes
  match the reference, and existing native libraries are byte-identical to v27.
- Source manifest declares the separate non-exported native service.
- Store install/discovery, switch contracts, profile contract, CP candidate and
  nested-layout checks, Chinese metadata/glyph checks, archive/index matching,
  runtime rule/reference bytes and whitespace checks passed.

Packaged local store candidates: navassist 2.2.0, phone_vision 1.2.0, zh_cn 1.1.11.
No push requested. APK/asset hashes and build logs are in the local task artifact
folder cp-lane-local-20261029 outside the Git repository.

## Explicit limits

No Android JNI inference executed; no real Binder timeout/death test, real frames,
phone/native load, sustained latency/heat, model accuracy or road validation.
A native-process crash/abstention path is designed, compiled and statically
checked, not real-device verified. No simulator performance is claimed.
The two four-class heads only express a bounded candidate, not arbitrary total
lane counts or complete same-direction carriageways. The 0.1 logit-margin heuristic
is not a confidence calibration. Firmware compilation and device activation were
not performed. Last deployed code remains the previous map-feature version.
