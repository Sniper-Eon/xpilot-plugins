# HUD model feedback gap

User road report: CP model visibly responded in the C3 HUD, while the companion
showed no matching current lane. Source inspection confirmed the exact gap:
phoneLaneEvidence fed the HUD only; lane_position_request returned only the old
road-edge-qualified road_lane_position.json. User subsequently authorized model participation in navigation selection. Fresh model
indices now enter the route planner when the visible count matches the navigation
count, under the existing plugin and phone-lane switches. This is an estimate,
not proof of a complete road view. Absolute confirmation remains false. Missing,
stale or count-mismatched data clears this input without restoring stale geometry;
existing relative preparation and all physical checks remain in force.

Added an original-frame-timed, session/revision-bound model observation record and
an opt-in laneEstimate field. Legacy queries/ACKs remain unchanged because old APKs
strictly reject unknown ACK keys. New APKs send both queries for old-host fallback
and retain model evidence if legacy feedback arrives later. The separate model type
cannot masquerade as an absolute lane. Its original age bounds the display lifetime.
Single-frame operation remains; no geometric corroboration or three-frame wait is
reintroduced. BSM, paint, edge, driver and engagement rules are unchanged.

APK v30 shows model lane number/count, and can mark the estimated current lane and
compare with map recommendations only for matching counts/current route. Labels
explicitly say model estimate. Absence/expiry/malformed output clears the estimate.
The existing absolute position channel and its tests remain intact.

Specs were reconsulted from upstream AGENTS/XPILOT/plugin.py/manifest.py and store
CONTRIBUTING; hashes match the previous qualification report. The paired local host
remains b9dfad2f8fcf66119a444be52efd4b869616c0d1; no new hook, cereal or firmware
change is needed. Last verified deployed plugin source was d909990; no device
version is inferred from local branch state. Current device connection attempts
found neither C3 nor Android ADB, so this repair is local until reconnected.

Validation commands and final counts are recorded in the task report. The first
Python check failed on the missing feedback API; the added check now covers source
age, session/revision mismatch and immediate valid model feedback. UDP tests cover
explicit negotiation, legacy shape preservation and boolean-version rejection.
Android tests cover parsing, distinct estimate/absolute state, nonrenewable age,
malformed scope and phone display text. No new road validation was performed.

Final local validation: 840 plugin tests passed (tesla_mixed_control excluded as
in the prior host-compatibility check); Android 352 tests, 351 passed and 1 skipped.
APK v30 assembled successfully; 28 native-library/model entries byte-match v29.
Store E2E installed/discovered all 30 entries with no errors; runtime rule ABI
reference comparisons passed with no errors. No host or firmware changes.
C3 SSH timed out and ADB listed no devices; nothing installed or activated.
Model planner tests cover matching/mismatching lane counts, master-off, unknown
input, changing recommendation alignment, and preservation of absolute identity.
Same-count matching is an operational estimate, not independent validation of
whole-carriageway coverage. Road accuracy remains unvalidated for this revision.
