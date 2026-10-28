# CP side-object producer audit

Reference pins: navipilot latest-snapshot `91d77de4fd7650ebc76c38cf4b47ede503f6d0dc`,
Carrot `3615bf4bf40016f102e7d4af3745455a3791faa2`. This audits those sources;
it does not establish which source/version was used in an author's road demo.

The referenced Carrot process configuration starts
`openpilot.selfdrive.carrot.radar.radard_dpath`. Its DPathRadarD receives
physical RadarData points and calls DPathRadarController.update(). In
`radar_motion/controller.py`, `_display_leads` groups projected radar points
by path-relative lateral offset: within 1.8m center, left-positive outside
center left, right-negative right. `_pick_side` selects a qualifying side lead.
`radard_dpath.py` publishes these as leadLeft/leadRight and leadsLeft/leadsRight.
`primary.py::vision_lead_from_model` reads the first forward visual lead; it
does not generate the left/right radar groups from camera pixels.

The paired SP host publishes `radarTracks` (not Carrot's `liveTracks`) and has
only leadOne/leadTwo in standard radarState. Thus copying the Android fields
or adding serialization cannot itself provide the referenced side detections.
An available, valid sensor stream and compatible producer are prerequisites.
An empty/unsupported sensor stream must not be converted into a clear lane.

The Android AutoOvertakeManager consumes side lead status, distance/relative
speed, lane geometry, BSM, active authority and model metadata. Its return
functions contain permissive null-side-object fallbacks. Those fallbacks are
not evidence of observed clearance. Its update() also explicitly suspends
when complete control/model telemetry is unavailable on compact adapters.

The independent CP navigation plugin remains a candidate for navigation,
lamp preparation and bounded speed targets. Automatic passing/return remains
unavailable on the current bridge. No camera stream, new hardware support,
full Carrot radar replacement or fabricated active/clear-side fields are
introduced by this audit. Vehicle-specific settings and live observations
belong in the private deployment record, not this public document.
