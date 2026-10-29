# Lane feedback and lamp diagnosis

Failure contract before implementation:
- The legacy lanePosition channel stays unknown while a fresh enabled phone estimate exists; model ownership must replace it without falsely certifying an absolute position.
- A stale/route-mismatched model must clear the model-owned position immediately; disabling restores the existing geometric channel.
- A missing carState marking field must never become code zero/dashed; line types require genuine fresh codes and stay read-only.
- A current-lane UI branch still prints OEM unknown alongside a usable model index.
- A navigation lamp request is not proof of CAN transmission or physical feedback; record sender-stage evidence without changing signal, BSM, paint, driver or firmware gates.

Source/current device host b9dfad2; upstream developer/API hashes are retained privately. No new host hooks or firmware required. Keep data in integrated navassist under its master.

Diagnosis from this car: all relevant masters are enabled. Historical samples show fresh valid turn guidance and lateral-active requests while both physical blinkers remain false. Existing recordings lack template/build/firmware-stage evidence, so the exact cause remains unproven. The latest model-lane commit did not edit the Tesla lamp sender or firmware rules. Added bounded card-side nav.lamp diagnostics and phone display; frame generation is explicitly not described as proof of CAN/panda acceptance.

This host has neither carState marking field. New read-only bridge parses genuine supported codes if available; this car currently reports unknown, not fabricated dashed lines. No Tesla CAN line-usage field is relabeled as line style. Missing markings do not bypass OEM vetoes. No host/cereal/firmware modification.

Model-owned legacy lanePosition now carries current index/count, source cpPhoneVision, visibleCorridor scope, absoluteConfirmed=false and original 800ms freshness. Existing APK position slot and lane title consume it. Missing/expired model clears immediately, master-off restores geometry.

Upstream XPILOT/manifest changed during this task only to add optional requires.plugins. Local/running host remains b9dfad2; this plugin does not depend on that new field or API.

Validation: failure checks reproduced missing old-position override, missing optional line reader and missing sender diagnostics; then passed. JVM wire test exposed nested-marking incompatibility with the deliberately shallow ACK parser; flat bounded fields fixed it. 843 plugin tests passed (tesla_mixed_control excluded as prior host-compatibility gate); APK 354 tests with 1 skipped. Store E2E all 30 entries/no errors; runtime rules reference bytes, plugin-switch and Chinese metadata checks passed. Native/model assets unchanged. No new road validation.
