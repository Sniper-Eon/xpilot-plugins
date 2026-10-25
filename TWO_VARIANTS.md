# Two X-Pilot variants (user request 2026-10-25)

Both versions use the same Sniper-Eon/xpilot host, native SP controls and reviewed plugin code.
The source choice and companion app differ: CPdazi compatibility versus the existing TesNav/特会开.
Navigation-recommended lane changes, bounded turn-signal preparation, OEM/BSM vetoes, navigation ceilings,
traffic-light assistance, lighting/BMS/display and optional original single-camera phone detection stay.
Remove stereo/dual-camera ranging and speed experiments, automatic passing and return-to-original-lane features.
Keep training/drive evidence outside deployment artifacts; Git history remains the rollback record.

Before implementation, required failure cases:
- A bundle is accidentally based on old SP or the legacy checkout rather than xpilot.
- Both phone sources issue turn requests simultaneously or phone-source selection silently falls back.
- CP protocol accepts replayed, stale, unbound or malformed navigation and creates an active request.
- A heartbeat renews old source observations; reconnects or route changes inherit stale lane state.
- Native blindspot false/missing becomes fabricated rear clearance, position or speed.
- CP discovery/handshake displays fake execution authority or advertises unsupported image/control abilities.
- Removed stereo/passing code survives in packaged app, services, endpoints or native OpenCV dependency.
- Cleanup removes original single-camera detection or route-guided lane changes.
- Profiles differ in ordinary features, or auto-install over a moving device is inferred from building variants.
- Native TN archives compile but the actual host store rejects a >400-line tuning module. Keep the public tuning API unchanged when extracting value declarations; verify through the real installer and native solver exercise.

Evidence: actual socket handshakes and expiry tests, archive/source structural check, unchanged navigation
regressions, Android build/unit checks, paired store install/discovery, and distinct profile metadata.
Source compatibility is not a claim of actual phone/road validation. CP cloud licensing remains with its app.
