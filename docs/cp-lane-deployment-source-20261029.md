# CP lane deployment follow-up source

User explicitly authorized deployment, then removed geometric corroboration and
the three-frame wait immediately, and explicitly chose switching CP -> TesNav.
navassist 2.2.2 provides fresh single-frame estimates without either confirmation.
Native BSM, paint, physical road-edge, driver, engagement and firmware limits stay.

The device preimage guard detected independent on-device model-only lane display
changes in hud/process/ui plus lane_geometry.py and lane_tracker.py. Installation
stopped before changing live files. These were read, merged and retained in source.
With phone lane mode enabled, the old geometry display tracker is explicitly reset
and not run; disabling phone lane mode retains the prior device geometry display.
This does not promote visible-corridor classification into an absolute map lane.

The native smoke failed on v28 due to two missing libVAE dependencies. v29 packages
the complete four-library closure from the user's reference; existing application
native libraries and signing identity remain byte/certificate compatible. Both day
and night JNI inference passed on the actual phone using a synthetic gray image.
The first check failed before the fix, and a static ELF-closure check also fails on
the original incomplete asset directory and passes the corrected directory.
No recognition accuracy is inferred from this smoke test.

Full plugin regression: 841 passed. Matching tenengkai JVM suite: 350 total,
349 passed, 1 skipped. Source-only model libraries remain private external build
inputs. No private weights, APK, keys or settings are committed. Current actual
installation/activation, source hashes and backup paths are tracked in the private
workspace cp-lane-deployment-20261029 report. Firmware is not changed.
