"""Wait for the two-seed gate; never train full-size following a failed gate."""
import json,subprocess,time
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];out=ROOT/'learning-runs/remembered-grid'
while True:
 path=ROOT/'results/symbolic-ppo-durability-gate.json'
 if path.exists():
  gate=json.loads(path.read_text())
  if gate['complete']:break
 time.sleep(5)
if not gate['passed']:
 print('Durability gate failed: full-size stage NOT launched; troubleshoot first.',flush=True)
 raise SystemExit(0)
# Both seeds must pass; choose seed 0 in advance rather than selecting by test scores.
for script,args,name in [
 ('preflight.py',[],'symbolic-small-preflight'),
 ('check_fullsize_navigation.py',[],'symbolic-fullsize-preflight'),
 ('symbolic_ppo.py',['--fullsize','--source',str(out/'symbolic-ppo-durable-seed0/latest.pt'),'--mode','detached_critic','--gae-lambda','1','--limit','1024','--decisions','1000000','--name','symbolic-ppo-fullsize-seed0'],'symbolic-ppo-fullsize-seed0')]:
 with (out/f'{name}.log').open('w') as f:
  subprocess.run([str(ROOT/'.venv/bin/python'),str(HERE/script),*args],stdout=f,stderr=subprocess.STDOUT,check=True)
 print('completed',name,flush=True)
