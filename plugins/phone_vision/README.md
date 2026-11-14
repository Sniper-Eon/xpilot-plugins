# Phone Vision: single-camera transport

Opt-in transport for the TesNav phone model. Default off. Single wide camera only, width 640 (optional 320),
4 frames/second cap. No camera buffer mapping until a phone requests a frame; idle requests expire.
Navigation remains an independent plugin and does not start image capture.

HTTP 8767 keeps the existing connection-code authentication and frame/observation format. A private existing
`/data/phone-vision/connection-code` can be reused during migration; never publish it. Otherwise the plugin
creates its private token. Phone observations expire after 800 ms and never grant lane clearance.

R12 phones keep the original JPEG JSON. New clients may explicitly negotiate lossless gzip JSON; the old
phone does not incur that compression work. Actual CPU load while serving frames still needs C3 measurement.
This migration does not claim the old capture-related model-lag incident is solved. Leave capture off until
parked load validation passes. Do not run this plugin alongside the legacy port-8767 bridge.

Dual-camera endpoints and workers have been removed. Automatic overtaking is not part of either profile. The companion app source
and model are under `companion/tesnav`; APK files are distributed as release assets, not Git source blobs.

OpenCV is loaded only after real image demand. The worker can reuse the existing private bridge packages
under `/data/phone-vision/pydeps` and `/data/wide-capture/pydeps` when the main device venv lacks OpenCV.
No packages are installed and the host process search path is not modified. Missing/broken dependencies
leave the observation unavailable; enabling the plugin is not proof that camera capture works.

## Optional CP lane observations (1.2.0, local candidate)

The existing authenticated `/v1/observation` may include `lane_cp`. Request token,
frame identity, original capture age, ordering and stream lifetime apply unchanged.
The payload is bounded to known day/night profiles and two 1..3 classes; derived
numbers must match and `scope=visibleCorridor`, `control_eligible=false` are mandatory.
Missing/null lane output clears it; no output can grant lane clearance. Side vehicle
observations keep their original contract. No new capture or automatic switch enabling.

## Optional side distance and speed (1.2.1)

A side object may also include `distance_m`, `relative_speed_mps`, `absolute_speed_mps`,
`track_id`, `track_hits`, `track_confidence` and `age_ms`. These describe the nearest
confirmed vehicle in the forward wide camera's side-front view. `hits`, `confidence` and
`occupied` are unchanged and remain the blind-spot occupancy contract. Missing or rejected
speed fields are omitted; they are not an empty lane and they do not grant clearance.
`age_ms` is how old that speed sample is. The forward wide camera does not see vehicles behind.
