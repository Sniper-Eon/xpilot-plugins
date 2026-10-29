# CP lane model: local-only integration candidate

This adapter invokes the CP 8.0.20 compact lane JNI ABI in a separate, non-exported
`:cp_lane` process. A worker crash cannot directly terminate the navigation process.
The existing phone vision session supplies one C3 wide JPEG; RGB is converted to
limited-range I420-style Y, with width used as stride. No stereo, extra C3 model or
second camera is started. This differs from CP's original decoded WebRTC Y plane;
JPEG conversion, crop/FOV, latency and model accuracy require real validation.

## Local reference assets

The reference APK is user-provided. Its source hash, extracted library/model hashes
and file list are recorded in the local generated `cp-lane-assets.json`. Reference
binaries/weights and APKs are NOT committed or uploaded. This source contains an
independent minimal JNI declaration and adapter, not copied CP application code.
No claim is made that the APK native/model assets inherit the public repo license.

Prepare into a NEW directory outside the Git checkout:

```sh
python3 tools/prepare_cp_lane_reference.py --apk /absolute/path/reference.apk --output /absolute/path/private-assets
./gradlew :app:testDebugUnitTest :app:assembleTenengkai -PCP_LANE_REFERENCE_DIR=/absolute/path/private-assets
```

The explicit build property adds assets/jniLibs only to the existing tenengkai variant.
Without it, normal builds still work; enabling model observation reports unavailable.
No downloads, assets overwrite or key/signature changes. v28 retains the existing
package, signing identity and X glass icon. Private credentials remain outside source.

## Behavior

Phone vision has two opt-in controls: lane estimation and explicit day/night profile.
Both are local phone choices; they do not enable any C3 plugin. JPEG decoding, side
vehicle detection and frame-bound HTTP posting are reused. JNI is lazy, single-flight,
with a 500 ms result timeout and no queue or old-result reuse. A late reply may finish
but is not attached to a later image; a hung worker prevents more requests rather than
accumulating work. Stopping the vision session unbinds it. Errors or absent assets yield
no lane candidate and do not authorize anything. Native execution is not proven by a
successful build/symbol check, and process isolation is not full fault/performance QA.

CP's wrapper exposes two groups of four scores; class 0 is unknown and classes 1..3
produce candidate laneNumber=leftClass and laneCount=leftClass+rightClass-1. This
representation is bounded (at most five lanes), not a general carriageway census.
We reject non-finite, tied or insufficient-margin scores; the 0.1 score margin is an
abstention heuristic, not calibrated probability. No confidence or absolute-position
claim is fabricated. Retuning requires held-out, labelled real images.

The optional `lane_cp` HTTP member carries only these bounded fields, profile and
`scope=visibleCorridor`, `control_eligible=false`. It shares the existing authenticated
request/frame token. C3 supplies the original capture timestamp and stream identity;
the phone cannot renew age or invent a new timestamp. Missing/null observations clear
lane evidence on the next accepted result. The 800 ms source-age gate still applies.

`navassist` owns its default-off `ExtNavAssistPhoneLane` setting. It needs a separately
enabled/working phone_vision source. Three distinct consistent source frames are
required, with route/stream changes, disabled settings, bad output and expiry clearing
the estimate. A repeated frame with a changed timestamp is rejected. HUD shows a model
estimate; only agreement with the independently qualified existing geometric absolute
position changes that label to corroborated. No model-only absolute promotion, no new
lane safety permission, no recommendation-to-observation conversion or actuation.
Camera position feedback still uses the existing qualified geometry contract.

## Validation boundary

Python transport-to-HUD replay and Kotlin postprocessing tests run locally. APK
packaging, signature, old native-library byte preservation and ELF/JNI exports checked.
No Android JNI inference, Binder death/timeout execution, phone load/heat/latency,
recognition accuracy, device deployment or road validation performed. Local candidate
only, with both model opt-ins default off.

## User update, 2026-10-29

navassist 2.2.1 removes the three-frame wait and geometric corroboration label.
Fresh valid single-frame output is displayed immediately as an estimate. The
previous three-frame/corroboration description is historical for 2.2.0 only.
The user also authorized deployment in the following task; actual installed and
verified states are recorded in that deployment report, not inferred from this doc.
