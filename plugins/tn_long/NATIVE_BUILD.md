# C3 native build

Built on 2026-10-25 on aarch64, CPython 3.12.3, AGNOS 19.7, in an isolated folder.
The existing build_native.py generated both solvers with comma-deps-acados 0.2.2.post98 and CasADi 3.6.7.
The host candidate was 0b49f127a0f90ecd13fc2c015a7afde3a6e6428e. No firmware or device launcher was changed.
The actual X-Pilot store installed the archive in both isolated profiles. Three ten-cycle solver exercises
(standstill, 15 m/s free road, 25 m/s with a slower lead) returned status 0 and finite output.
This is a smoke check, not a control-performance or road-acceptance claim.

Runtime libraries are unmodified copies of the comma-deps-acados wheel pinned in the host uv.lock.
The generated solver and Cython wrappers are reproduced by build_native.py.
Upstream notices are in licenses/. Source projects: [acados](https://github.com/acados/acados),
[BLASFEO](https://github.com/giaf/blasfeo), [HPIPM](https://github.com/giaf/hpipm),
[qpOASES](https://github.com/acados/qpOASES). Shared libraries remain individually replaceable.
