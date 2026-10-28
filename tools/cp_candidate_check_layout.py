"""Failures first: CI nests the paired host under the plugin checkout; a
hard-coded sibling path ignores X and fails before any candidate check runs.
Run the actual package E2E CLI from a disposable CI-shaped directory.
"""
import json,os,shutil,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
HOST=Path(os.environ.get('X',ROOT.parent/'xpilot')).resolve()
with tempfile.TemporaryDirectory(prefix='cp-ci-layout-') as temp:
 root=Path(temp)/'plugins-checkout';(root/'tools').mkdir(parents=True);(root/'dist').mkdir()
 shutil.copyfile(ROOT/'tools/cp_candidate_check.py',root/'tools/cp_candidate_check.py')
 shutil.copyfile(ROOT/'index.json',root/'index.json')
 entries=json.loads((ROOT/'index.json').read_text())['plugins']
 for d in entries:
  if d['id'] in ('cp_nav','navassist'):
   name=f"{d['id']}-{d['version']}.tar.gz";shutil.copyfile(ROOT/'dist'/name,root/'dist'/name)
 env=dict(os.environ,X=str(HOST),PYTHONPATH='')
 result=subprocess.run([sys.executable,str(root/'tools/cp_candidate_check.py')],cwd=root,env=env,capture_output=True,text=True)
 assert result.returncode==0,result.stdout+result.stderr
 print(json.dumps({'nested_host_layout':True,'exit':result.returncode}))
