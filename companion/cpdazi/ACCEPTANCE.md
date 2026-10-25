# CP phone reconstruction: candidate acceptance

Requested: a CP-derived Android companion and the actual CP navigation policy,
both integrated with X-Pilot. A TesNav APK with a CP label does not satisfy this.

Failure modes, recorded before fork modifications:

1. Public phone source differs from the supplied 8.0.20 binary. Record both
   revisions; do not claim bit-for-bit or behavioral equivalence without evidence.
2. Reintroducing AutoOvertakeManager restores functions the user cancelled.
   Remove its executable class, lifecycle wiring and mode button. Keep navigation.
3. Automatic camera streaming recreates C3 frame-drop pressure. This variant uses
   native telemetry only; no camera socket is opened by the companion.
4. Old telemetry or disconnected BSM must not be displayed as a fresh clear lane.
   Arrival of hello/ping is not arrival of vehicle data. Clear data on disconnect
   or expiry. BSM inactive is not a clearance measurement.
5. Wrong identity/signature creates extra icons or breaks updates. Use the owner's
   existing companion applicationId and signing key, one launcher, distinct label.
6. CP Carrot parameters, remote commands and unsupported SP fields differ. Never
   fake successful writes or fabricate missing sensor data; park/control tests
   remain pending until the paired policy and settings adapters are implemented.
7. Leaking upstream/private credentials or silently sending telemetry is not
   needed for navigation. Read credentials locally; no publisher OAuth credentials.
8. A successful Android compile does not prove phone/C3 interoperation or road
   safety. Record build, protocol replay, installation and road validation apart.

Validation order: source contracts first, original upstream compilation, fork
compilation/unit tests, APK identity/signature/DEX inspection, real websocket
replay, parked phone/C3 checks, then separate road acceptance. No control enable
or device restart is part of the phone source/build step.
