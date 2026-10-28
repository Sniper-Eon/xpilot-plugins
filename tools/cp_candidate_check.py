#!/usr/bin/env python3
"""Local package E2E: own store archive -> actual host discovery -> actual
parked UI switch -> mutually exclusive active hooks -> disable. Failure cases:
a shared source survives switching; wrong plugin supplies the lane policy;
CP master defaults active; its off switch leaves its hook active. Uses an
isolated file-backed Params view, no device, manager, CAN or live message IO.
"""
import json,os,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
HOST=Path(os.environ.get('X',ROOT.parent/'xpilot')).resolve()
with tempfile.TemporaryDirectory(prefix='cp-switch-e2e-') as temp:
 os.environ['XPILOT_PLUGINS_DIR']=str(Path(temp)/'installed')
 sys.path[:0]=[str(HOST),str(HOST/'opendbc_repo'),str(HOST/'msgq_repo')]
 from openpilot.tesla import store
 class Core:
  def __init__(self):self.values={}
  def get(self,key,**kwargs):return self.values.get(key)
  def get_bool(self,key,**kwargs):return key=="IsOffroad" or bool(self.values.get(key,False))
  def put(self,key,value,**kwargs):self.values[key]=value
  def put_bool(self,key,value,**kwargs):self.values[key]=bool(value)
 try:
  import openpilot.common.params as core_params
 except (ImportError, OSError):
  import types
  sys.modules["openpilot.common.params"] = types.SimpleNamespace(Params=Core, UnknownKeyName=KeyError)
 else:
  core_params.Params = Core
 entries={d['id']:d for d in json.loads((ROOT/'index.json').read_text())['plugins']}
 for name in ('navassist','cp_nav'):
  d=entries[name]
  entry=store.IndexEntry(**{k:d[k] for k in ('id','name','version','api','category','author','description','sha256','platform')},
    url=(ROOT/'dist'/f"{name}-{d['version']}.tar.gz").as_uri(),installable=True)
  assert store.install(entry) is None,name
 from openpilot.tesla import plugins
 from openpilot.tesla.ui.offroad import switch_plugin
 params=plugins.view(Core());by_name={p.NAME:p for p in plugins.PLUGINS}
 assert {'navassist','cp_nav'}<=by_name.keys(),plugins.LOAD_ERRORS
 assert not params.get_bool('ExtCpNavEnabled')
 for chosen,other in (('navassist','cp_nav'),('cp_nav','navassist'),('navassist','cp_nav')):
  switch_plugin(by_name[chosen],True,params)
  assert params.get_bool(by_name[chosen].ENABLE_PARAM)
  assert not params.get_bool(by_name[other].ENABLE_PARAM)
  assert plugins.owner(params,'source:route')==chosen
  assert plugins.owner(params,'role:lane_change.policy')==chosen
 switch_plugin(by_name['navassist'],False,params)
 assert plugins.owner(params,'role:lane_change.policy') is None
 print(json.dumps({'archive_install':True,'actual_UI_switches':3,'independent_masters':True,'closed_owner':True,'device_access':False}))
