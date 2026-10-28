"""Failures first: a replacement TN planner loses all enabled plugin targets,
so CP/TesNav/SCCV appear configured but do not constrain its cruise candidate.
Exercise the actual TN wrapper and actual host target merger with a solver-free
planner fixture; no native solver, live message publisher or vehicle involved.
"""
import sys
from types import ModuleType,SimpleNamespace as N
from openpilot.tesla import plugins as host
from openpilot.cereal import custom
from tn_long.plugin import _TnPlanner


def test_tn_wrapper_collects_navigation_targets_without_bypassing_lead_caps(monkeypatch):
 source=custom.LongitudinalPlanSP.LongitudinalPlanSource
 class Target:
  def update(self,sm,v_ego,v_cruise):return 100/3.6
 target=Target();seen=[]
 monkeypatch.setattr(host,'long_targets',lambda CP,params:seen.append((CP,params)) or [target])
 class Planner:
  def __init__(self,CP,CP_SP):
   self.mpc=N(configure_runtime_tuning=lambda *args:None);self.plugin_long_targets=[]
  def update(self,sm):
   self.candidates=host.apply_long_targets(self.plugin_long_targets,sm,
      {source.cruise:(60/3.6,0.),source.sccVision:(80/3.6,0.)},20.,0.,60/3.6)
   self.v_desired_trajectory=[min(v[0] for v in self.candidates.values())]
   self.a_desired_trajectory=[0.];self.j_desired_trajectory=[0.];self.output_a_target=0.;self.output_should_stop=False
 module=ModuleType('tn_long.tn_no_dec.planner');module.LongitudinalPlanner=Planner
 monkeypatch.setitem(sys.modules,module.__name__,module)
 CP=N(brand='tesla');params=object();wrapper=_TnPlanner(CP,N(),params)
 sm={'carState':N(gasPressed=False,brakePressed=False),'carControl':N(enabled=True,cruiseControl=N(override=False))}
 result=wrapper.update(sm,None)
 assert seen==[(CP,params)]
 assert wrapper.planner.candidates[source.cruise][0]==100/3.6
 assert result.speeds==[80/3.6]  # other host/SP speed caps still win
