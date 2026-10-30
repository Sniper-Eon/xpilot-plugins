# Blendful Lane Center

Port of sunnypilot's alpha Blendful lane-center policy (PR #2073, commit
`97135965`) to the xpilot plugin library.

- Control: `lat.correction` adds a small curvature correction toward the visual
  lane center. The xpilot host caps the total correction at 0.5 m/s² and SP's
  `clip_curvature` still runs afterwards.
- Display: `RoadOverlay` draws the same center line in blue `(0, 200, 255)`.
- Only active while lateral is active, `vEgo >= 5 m/s`, and the model
  `laneChangeState` is `off`.
- Default disabled. Enable while parked, then restart.

This is not a byte-for-byte copy of sunnypilot's modeld implementation: xpilot
computes the correction in `controlsd` through the plugin hook, using the
published `modelV2` lane lines. Validate on road; the upstream feature is alpha.

Source authors: Discountchubbs (math), royjr (initial implementation/UI),
nayan8teen (UI), rav4kumar (testing), sunnypilot contributors. MIT licensed.
