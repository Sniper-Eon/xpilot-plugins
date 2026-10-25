# X-Pilot CP companion — reconstruction candidate

Forked from [jixiexiaoge/navipilot, Amapauto](https://github.com/jixiexiaoge/navipilot/tree/3f1af5f50bfb3c414aa40b9ab48a2fe6cf5afbda).
Original CP / Navipilot author: JiXieXiaoGe and contributors. Their MIT declaration
is preserved in UPSTREAM_README.md; modifications are a Sniper-Eon X-Pilot fork,
not an official CP release.

This is **not** a rebuild of the supplied 8.0.20 APK: its embedded source revision
`c0ced663b5cbc6c3fc4a28f369c6805751067eed` is different and was not obtainable from
the public repository. The full alternate public branch was also examined, but
it predates Amapauto and has different navigation and telemetry protocols.

Implemented in this source candidate:

- Original CP Amap Auto broadcast handling, UI and v2 navigation sender.
- Owner companion applicationId, distinct `X-Pilot CP导航` label, release signing
  from local Gradle properties. It replaces the owner's TesNav variant rather
  than installing another launcher. The two variants cannot run simultaneously.
- AutoOvertakeManager, startup/update wiring and its mode selector removed.
- Native C3 BSM via compact carState metadata, without camera subscriptions.
  The public UI bridge's hardcoded false BSM values now pass through real flags.
- Missing, expired or disconnected vehicle metadata clears the displayed state;
  false BSM means not triggered, not safe rear clearance.

Not completed: exact 8.0.20 parity, CP-native vehicle navigation policy,
restricted remote settings/command mapping, full geometric lane telemetry,
per-source navigation freshness (the public exporter timestamps snapshots at send time),
foreground-service restart ownership, real-phone install/interoperation and onroad validation. The deployed C3 remains
in observation mode. Do not enable controls based on compilation alone.

Seven historical upstream tests refer to pre-Amapauto packages/modules that are
absent in the pinned source. They are preserved under `upstream-tests-unported/`,
not counted as passing tests. The build does not run detekt; its upstream plugin
is not required for APK assembly. Android Gradle Plugin is updated from 8.6.0 to
9.3.1 with its Kotlin 2.2.10 runtime and the installed SDK 37 / Gradle 9.5 / Java 17 toolchain. The target Android API remains 35.

Build with Android SDK 37, Java 17, Gradle 9.5 and existing local properties
`LANETEST_STORE_FILE`, `LANETEST_STORE_PASSWORD` (alias `tesnavtest`):

```
gradle :app:testDebugUnitTest :app:assembleRelease
python3 -m unittest discover -s tests -v
```

Do not publish local signing material. Release APKs belong in GitHub Releases,
not the source tree. See ACCEPTANCE.md for pre-implementation failure modes.

## Validation status (2026-10-25)

Android compile and signed APK packaging succeeded. Five source contracts and
three JVM telemetry tests pass. Release lint remains **not validated** because
five lint-tool JARs were unavailable offline (IntelliJ core, lint Kotlin compiler,
UAST, Kotlin reflect and play-sdk-proto); the online download was incomplete.
The candidate APK was assembled with only the three lintVital tasks excluded.
This is not a completed release check and must be resolved before deployment.
No phone was connected to ADB; no APK was installed and no C3 settings changed.
