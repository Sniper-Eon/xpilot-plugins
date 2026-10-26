# User-fork plugin development

- Follow the workspace AGENTS.md and paired `../xpilot/XPILOT.md` first.
- Work in this checkout on `main`; do not create another branch/worktree unless requested.
- Inspect status before edits. Keep coherent changes in scoped commits; push only when requested.
- Every store plugin must own a unique BOOL `enable_param`. Optional vehicle behavior belongs in plugins, not hard-coded host paths. Verify disabling, missing dependencies and faults as well as enabling. Missing/stale inputs must not become permission to control.
- User decision 2026-10-26: keep navigation lane positioning, physical signals, maneuver slowdown, chime and display together in ONE `navassist` plugin, with master `ExtNavAssistEnabled` and its existing internal settings. Do not split that group into separate plugins. Other feature groups keep their own plugin switches.
- Phone companion source/adapters may remain in `companion/`; phone installation must not silently enable C3 features. Keep DS's device engagement fixes, parked settings and Chinese UI.
- Read CONTRIBUTING.md for archive/index generation and paired-host validation. Write failure contracts/checks before implementation; prefer meaningful integration checks. Do not create unit tests after implementing the behavior.
- Keep source, local checks, firmware compilation, device installation/activation and road validation distinct. No deployment is implied by a source change. Preserve private settings, device keys and driving logs outside Git.
