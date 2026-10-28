# Upstream synchronization — 2026-10-28

Source baselines: onemiless/xpilot:xpilot at 1de0b807d1ffde580dd2fd19f49b2f18b329e794;
onemiless/xpilot-plugins:main at 36f2bfedca506ef86b79701c550820ef1f8a1a06.
Paired user host: f451a13b219930e26d316b8997dafda93fc6784f.

Preserved Chinese localization, integrated TesNav navassist, independent CP navigation,
phone package identity and DS engagement repairs. CP 0.2.0 and navassist 2.0.0 use
canonical NAV runtime rules (ABI 1). Navigation signal producers are exclusive.
New optional upstream plugins remain disabled in the staging profiles. Phone vision
1.1.1 and Chinese UI 1.1.9 declare the new paired-host usage metadata.

Local plugin suite: 779 passed. Package switching, Chinese metadata (159 fields),
archive integrity, canonical runtime-rule bytes and isolated profile staging checked.
Host native safety, C++ rule-loader, longitudinal replay and firmware build evidence
is recorded separately in the paired host docs/validation/upstream-sync-20261028/REPORT.md.
GitHub Linux CI is an additional release gate, not implied by these local results.

No device, phone or live firmware was changed by this synchronization. The old device
host must not install these packages alone: a coherent ABI-1 host/store/firmware set
needs qualification. Active navigation signals require primary cruise engagement;
the older MADS-only permission is not equivalent. Phone CP handshake, physical
engagement and road behavior still require device validation before deployment.
