"""Two real X-Pilot profiles and removed-feature build contract, specified first."""

from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
errors = []
app = ROOT / "companion/tesnav/app"
for name in (
  "DualCameraSession.kt",
  "DualGroundCore.kt",
  "PhoneStereoMatcher.kt",
  "StereoRayGeometry.kt",
  "AutoOvertakeDecider.kt",
):
  if list((app / "src/main").rglob(name)):
    errors.append("Cancelled source remains: " + name)
for path, words in [
  (app / "build.gradle.kts", ("org.opencv", "phoneStereo")),
  (app / "src/main/kotlin/com/garan/tesnav/vision/PhoneVisionActivity.kt", ("dual_camera", "双相机观察")),
  (ROOT / "plugins/phone_vision/transport.py", ("/v2/pair", "/v2/observation")),
]:
  for word in words:
    if word in path.read_text():
      errors.append(f"Cancelled entry {word} in {path.relative_to(ROOT)}")
for name in (
  "PhoneVehicleDetector.kt",
  "PhoneVisionService.kt",
  "SideVehicleCore.kt",
  "NavigationForegroundService.kt",
):
  if not list((app / "src/main").rglob(name)):
    errors.append("Original feature missing: " + name)
for name in ("cpdazi", "tesnav"):
  p = ROOT / "profiles" / f"xpilot-{name}.json"
  if not p.exists():
    errors.append("Missing variant: " + name)
    continue
  d = json.loads(p.read_text())
  if d.get("host") != "Sniper-Eon/xpilot" or d.get("source") != name:
    errors.append("Wrong base/source: " + name)
  if d.get("removed") != ["stereo", "automatic_overtaking"]:
    errors.append("Wrong removals: " + name)
profiles = [json.loads((ROOT / "profiles" / f"xpilot-{name}.json").read_text()) for name in ("cpdazi", "tesnav")]
if profiles[0]["plugins"] != profiles[1]["plugins"]:
  errors.append("Ordinary feature lists differ")
for d in profiles:
  expected = "1" if d["source"] == "cpdazi" else "0"
  if d["params"].get("ExtNavAssistSource") != expected:
    errors.append("Wrong exclusive navigation source: " + d["id"])
  for key in ("ExtNavAssistLaneChange", "ExtNavAssistTurnSignal", "ExtNavAssistTurnSlowdown", "ExtPhoneVisionEnabled"):
    if d["params"].get(key) != "0":
      errors.append("Candidate enables an unvalidated active feature: " + key)

print(json.dumps({"errors": errors}, indent=2))
raise SystemExit(bool(errors))
