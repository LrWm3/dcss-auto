"""Wait for gradient controls, then isolate complete-return advantage targets."""
import subprocess,time
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
while not (ROOT/'results/symbolic-ppo-cause-actor_only_retry.json').exists():time.sleep(5)
for mode in ('joint','detached_critic','actor_only'):
 name='symbolic-ppo-cause-mc-'+mode
 with (ROOT/'learning-runs/remembered-grid'/f'{name}.log').open('w') as f:
  subprocess.run([str(ROOT/'.venv/bin/python'),str(HERE/'symbolic_ppo.py'),'--mode',mode,'--name',name,'--decisions','500000','--gae-lambda','1'],stdout=f,stderr=subprocess.STDOUT,check=True)
with (ROOT/'learning-runs/remembered-grid/symbolic-ppo-cause-audit.log').open('w') as f:
 subprocess.run([str(ROOT/'.venv/bin/python'),str(HERE/'symbolic_ppo_audit.py')],stdout=f,stderr=subprocess.STDOUT,check=True)
