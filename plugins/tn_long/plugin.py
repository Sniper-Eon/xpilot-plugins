"""TN longitudinal (TN-NoDEC) as an xpilot long_planner plugin (role:long.planner).

Runs the TN planner (legacy cruise-obstacle MPC + TN acceleration controller, with its own lead following) on the
same sm as SP's planner, and hands its trajectories to the host, which replaces SP's plan (aTarget clipped to
ACCEL_MIN/MAX; SP's MPC still decides FCW). The acados solvers are prebuilt binaries (see build_native.py), so the
manifest's platform must match the device. Not ported: TN's controlsd stopping policy (no plugin hook for it).
"""
from types import SimpleNamespace

from openpilot.tesla.plugin import Plugin


class _TnPlanner:
  def __init__(self, CP, CP_SP, params):
    from .registry import TN_NO_DEC_BACKEND
    from .tn_no_dec.planner import LongitudinalPlanner
    self.planner = LongitudinalPlanner(CP, CP_SP)
    from openpilot.tesla import plugins
    self.planner.plugin_long_targets = plugins.long_targets(CP, params)
    self.planner.mpc.configure_runtime_tuning(params, TN_NO_DEC_BACKEND)

  def update(self, sm, sp):
    p = self.planner
    p.update(sm)
    return SimpleNamespace(speeds=p.v_desired_trajectory, accels=p.a_desired_trajectory, jerks=p.j_desired_trajectory,
                           a_target=float(p.output_a_target), should_stop=bool(p.output_should_stop))


class TnLong(Plugin):
  @classmethod
  def long_planner(cls, CP, CP_SP, params):
    return _TnPlanner(CP, CP_SP, params)
