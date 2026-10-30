# Official navigation model input trial — 2026-10-30

Offline developer tool only: `tools/nav_model_trial.py`. No manager registration,
plugin manifest, Params changes, vehicle control, model selection or deployment.
This is the first input experiment, not completed xpilot model integration.

Reference reviewed: commaai/openpilot nav-model-integration
`afbf2e547e9319e2eb9f515e1e4330af63705cec`; xpilot upstream
`716847fbb76372f67f398c5171744d21bb424ee3`; plugin upstream
`503ce9c4a4d0256762ecbbc7d9472528bbe28d54`.
Local host `95f8d3e5231b360903203798c6f14cefa7218d05`, plugin base
`a3c1737dd931fb882b929118a36f92a8087aee2c`. Upstream AGENTS, XPILOT hard
rules/model role, plugin.py, manifest.py and contributing rules were reviewed.
Device active version remains unqueried; upstream compatibility is not inferred.

The tool writes float32 nav_map [1,1,256,256], preserving grayscale 0..255,
and navigation [1,47]. It uses official maneuver selection/Valhalla encoding,
including skipping merge, and compensates instruction distance for elapsed time.
The experiment requires both map and instruction valid and fresh, matching
session/revision/route, qualified positioning and realtime mode. Future timestamps,
malformed data, empty maps and disable produce no tensor file. These gates are
experimental admission, not proof of permission to drive or synchronized capture.
No input is retained across calls. Unknown modifier fallback follows upstream.

CLI: `python -m tools.nav_model_trial request.json map.png NEW_OUTPUT_DIRECTORY`.
Use Python with the existing numpy and Pillow dependencies. The request schema is:

```json
{"nav":{"context":{"session":"s","revision":1,"route":"r"},"mono":10,"valid":true,"positioningQualified":true,"mode":"realtime","maneuvers":[{"type":"turn","modifier":"right","distance":100}]},"frame":{"context":{"session":"s","revision":1,"route":"r"},"mono":10,"valid":true},"now":10.1,"speed":10,"enabled":true}
```

Times are seconds on the SAME monotonic clock; external capture timestamps must
be translated and verified before using this envelope. Booleans in JSON are
fixture assertions, not authenticated vehicle authorization. Images must already
be 256x256 grayscale in the model's map convention; no resizing or coordinate
conversion is silently performed. Output is only two optional inputs, not all
11 model inputs. Route transfer currently used by navassist is display-only;
this tool does not promote it to control or consume its simplified geometry.

Validation (bundled Python 3.12):
- Before implementation: unittest command failed importing the absent feature (exit 1).
- `python -m unittest tools.tests.test_nav_model_trial`: 8 tests pass (exit 0).
- 600 combinations compared against the pinned, downloaded official helper:
  identical float32 navigation encoding (exit 0).
- CLI with historical Careland L/256x256 image and explicitly SYNTHETIC maneuver/
  clock/context produced optional-inputs.npz (exit 0); disable and mismatched route
  returned exit 2 and produced no tensors. This is NOT synchronized driving replay.
- `python3 tools/build_index.py --check`: exit 0; store artifacts unchanged.
- `git diff --check`: exit 0.
- All 23 paired-host *_check.py gates attempted. Results are in the private local
  trial directory gates.json. Most cannot execute with this desktop runtime
  (capnp/zmq/zstandard/opendbc missing); shared_safety_check also references the
  removed safety_problem API. Full host validation is NOT passed. Host source is
  unchanged; do not fix unrelated legacy gates as part of this input experiment.

Artifacts: sibling `official-nav-trial-20261030/` (kept outside public Git), with
reference helper, synthetic request, historical map, parity and CLI results.

Next: recover the actual weights (not included in the supplied ZIP), synchronized
camera/route/GPS capture and complete preprocessing/recurrent-state feeds. Confirm
matched ONNX vs compiled weights: the latest branch updated only the compiled
artifact after the historical ONNX. Then run actual inference and evaluate target
USB+AMD compatibility, timing and failure fallback. No GPU, firmware compilation,
device activation or road validation has occurred in this trial.
