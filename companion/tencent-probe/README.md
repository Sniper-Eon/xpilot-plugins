# Tencent legacy navigation observation bridge

Source preparation for the user's requested Tencent → integrated navassist switch.
**This v5 APK observes navigation; it does not yet replace TesNav or authorize driving.**
The running C3 remains unchanged. No vehicle permission is granted by installing this APK.

The supplied tc-v61 APK's `/app` callbacks were empty during the observed legacy UI
navigation. This bridge appends `NavViewDataManager.NavViewDataObserver`,
`LocationAPI.LocationObserver` and `HDLocationObserver` to existing instances. It
never replaces Tencent's single guidance listener or creates a new navigator.
Only original code/resources, a manifest Application wrapper and one additive DEX
are packaged; original APKs, keys and driving captures are deliberately excluded.

## Failure contract and verification

`tests/NavigationObservationsHostTest.java` checks unchanged callback clocks during
re-export, route replacement fencing, release, late-route rejection, missing-value
clearing and bounded retention. `tests/test_navigation_contract.py` failed on v4
before implementation and passes on v5. Existing APK preservation/observer tests
also pass locally. This establishes source/build properties, not road correctness.

The loopback-only `/navigation` endpoint exports callback arrival clocks separately
from raw source timestamps, route IDs, UI fields and native location/matching/HD
observations. Read-only `/health` and `/geometry` remain available. Polls and HTTP
reads do not renew callback times. UI release clears observations. At most 32 UI
event sections and one location/HD observation are retained.

`controlUsable=false`, `navigationMode=unknown`, `coordinateSystem=unknown_raw`
and `egoLaneIndexBase=unknown` are deliberate. UI navigation presence is not proof
of real navigation; a UI redraw is not a fresh navigation tick. SDK getters for HD
lane IDs retain their raw meanings until verified; lane-group counts and recommended
arrows are not the current lane count. Geometry remains diagnostic. Source timestamps
and matching fields must be checked with real navigation before a control adapter.

## Local build

Requires Android SDK 37/build-tools 37, JDK 17 and the user-supplied **original**
tc-v61 APK as `--base`. No base APK is downloaded or committed. The keystore must
match the installed probe; never uninstall an existing app to work around a mismatch.

```sh
python build_candidate.py --base /absolute/path/to/original-tc-v61.apk
TENCENT_BASE_APK=/absolute/path/to/original-tc-v61.apk \
GEOMETRY_APK="$PWD/out/tc-v61-navigation-observer-v5.apk" \
python -m pytest -q tests/test_apk_contract.py tests/test_callback_contract.py tests/test_navigation_contract.py
```

## Pending acceptance before actual switching

1. Real phone navigation versus built-in simulation/exit/recalculation: verify mode,
   route identity, source timestamps, matching, guidance step/distance/turn codes.
2. Verify geometry coordinate system/units, applicable road and current-lane basis;
   never map future junction lanes onto the current road without connection evidence.
3. Implement the verified adapter through existing TesNav v3 into navassist. Verify
   stale/missing/old-route/disable/driver override cases; retain native SP/BSM/paint,
   road-edge and engagement checks. Preserve 250/800/640/400 m planning thresholds.
4. Build/update the same TesNav package/signature and preserve pairing/settings/icon.
   Back up the running C3, activate only while parked, then report road validation
   separately. Existing high-confidence safety/DS/Chinese-localization fixes stay.

2026-11-22 device check: host API 1 / ABI 2 matches local; navassist 2.4.5-final.
The probe v5 is installed; actual navigation capture awaits phone unlock. No Tencent
navigation driving source has been activated. The earlier v4 geometry capture was
simulation-triggered cached guide-area geometry, not real ego-lane acceptance.
