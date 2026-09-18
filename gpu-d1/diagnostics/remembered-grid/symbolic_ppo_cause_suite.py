"""Sequential causal controls, identical seed and original source checkpoint."""
import os,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
for mode in ('critic_only','detached_critic','actor_only'):
 name='symbolic-ppo-cause-'+mode+('_retry' if mode=='actor_only' else '')
 log=ROOT/'learning-runs/remembered-grid'/f'{name}.log'
 with log.open('w') as f:
  subprocess.run([str(ROOT/'.venv/bin/python'),str(HERE/'symbolic_ppo.py'),'--mode',mode,'--name',name,'--decisions','500000'],stdout=f,stderr=subprocess.STDOUT,check=True)
