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

## Continuation: recurrent runner and actual artifact availability

Added `tools/nav_model_sequence.py`: pinned size and streaming SHA256 verification
before loading ONNX; validates every prepared frame against runtime input names,
dtypes and shapes before starting; initializes state heads to zero and advances
all next-state heads per frame; rejects malformed/nonfinite state/output. Saves
raw outputs and per-frame CPU timings without interpreting them as road accuracy.
Prepared NPZ contains each non-state input with an added leading frame dimension;
for example new_img is [T,2,6,128,256]. No camera warp is silently fabricated.

Validation:
- New failure contract initially failed importing absent runner (exit 1).
- Both unittest modules: 12 tests passed (exit 0).
- An actual ONNX Runtime session ran a deliberately tiny recurrence fixture for
  140 frames; output 1..140 exactly. This verifies runner state plumbing ONLY,
  and is explicitly not the official model or navigation performance.
- Store index check and diff whitespace check passed (exit 0).
- Prior paired-host gate limitations remain unresolved. No host or runtime plugin
  changed; no firmware, GPU, vehicle activation or road validation performed.
- Isolated environment in the sibling private trial directory now contains onnx
  and onnxruntime; repository runtime dependencies have not changed.

The expected 814591106-byte ONNX was NOT found locally. Its official LFS batch
request returns object 404. GitHub media and the official HuggingFace historical
content-addressed URL also return 404. HuggingFace main currently references a
DIFFERENT SHA256 and was deliberately not substituted. Official lfs-history
README reports deletion of 437 objects on 2026-10-19 and partial recovery;
this context does not establish why this particular object is unavailable.
The provided ZIP lists the weights and prepared camera frames as excluded external
files on the original Windows workspace. Existing local HEVC clips do not provide
verified matched route/GPS/preprocessing. Official inference remains unexecuted.

Recovery target: original big_driving_supercombo.onnx with SHA256
`1d18c42ea4cd95c8bffab4635844b78b8e2d4e25b9de44a9c5ac2e0961371a2e`,
plus verified prepared camera feeds or a matched capture with calibration. The
runner is ready for those inputs; no alternate model is silently accepted.

## Weight recovery completed

The previously missing ONNX has now been recovered from the release linked by
Deggory/openpilot-models-onnx README:
https://github.com/happymaj11r/openpilot-models/releases/download/big-nav-model-integration-1d18c42e/big_driving_supercombo.onnx

Downloaded into sibling private trial `weights/big_driving_supercombo.onnx`.
Size 814591106 and full SHA256
`1d18c42ea4cd95c8bffab4635844b78b8e2d4e25b9de44a9c5ac2e0961371a2e`
match the official pointer and research package. ONNX loaded successfully and all
11 input names/shapes match the historical inspection. This confirms the recovered
bytes, not merely the release label. Private recovery.json records provenance.
No inference or deployment was performed during retrieval.

Search covered Documents/Desktop/Downloads/cache filenames, exact-sized files in
Documents/Desktop/Downloads (including Git object directories), Spotlight exact
names, and 33 ZIP files across the project and accessible October WeChat file
folder. No original prepared-frames.npz was found. Existing ego*.npz contain only
time/speed arrays, not model camera tensors. Synchronized camera/route/GPS inputs
and target-GPU qualification remain outstanding; the missing-weight blocker is
resolved. No claim is made about unmounted Windows storage or inaccessible folders.

## Actual official CPU inference completed

Added repeatable end-to-end diagnostic `tools/nav_model_diagnostic.py` with failure
assertions declared before the experiment (nonfinite/missing states, ABI mismatch,
aliasing of shared history, nonrepeatability, and withdrawal history effects).
Run from the plugin repository with the isolated trial environment:

```
python -u -m tools.nav_model_diagnostic MODEL.onnx MAP.png NEW_OUTPUT_DIRECTORY
```

Actual pinned official ONNX inference: 474 invocations, CPUExecutionProvider,
all outputs finite. Includes 140 zero-input warmup frames, six single-frame
branches from identical copied history, then paired baseline vs 24 navigation-on
and 140 withdrawn-input frames. All five next-state tensors are carried forward.
Identical-history blank repeat was bit-exact and shared snapshot was unchanged.
Raw results: sibling `official-nav-trial-20261030/real-diagnostic/result.json` and
`outputs.npz`; model/map/source/output SHA256 recorded with the results.

Median inference 0.4520 s, P95 0.5079 s on this desktop CPU. This does not establish
20 Hz target-GPU operation. Input effects relative to the common blank baseline
were observed for map-only, left, right and nav-only branches. Statistics compare
RAW action/plan heads (including distribution parameters), not decoded physical
steering, actual road positioning error or driving quality.

After withdrawing BOTH map and navigation, action/plan heads still differed from
baseline at sampled withdrawn frames 1 and 20; sampled frames 60, 128 and 140 were
exactly equal. This is evidence that current-frame input removal is not immediate
history removal. It is NOT a universal 60-frame timeout or proof of a safe switch.
No state-reset or safety policy was added to the vehicle as a consequence.

Critical scope: all camera tensors were synthetic black, map was a historical
Careland image unrelated to any camera, traffic convention/action_t were fixed.
No synchronized road replay, camera warp verification, GPU compilation, installed
plugin path, device activation or road validation is claimed. Local model
execution and recurrent/input plumbing are now actually exercised; complete
xpilot navigation integration is still outstanding.

Checks on this final tool: 12 unittest cases passed, store index --check passed,
diff whitespace check passed. The real 474-inference experiment passed all embedded
assertions (exit 0). Paired-host full gate set attempted once again: 5/23 passed;
remaining environment/legacy-interface failures recorded in sibling
`host-gates-real/result.json`. Host source is unchanged; full host gates remain
unresolved and are not reported as passing.
