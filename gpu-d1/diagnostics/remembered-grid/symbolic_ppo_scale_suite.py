"""Two-seed durability test before any full-size map progression."""
import subprocess,json
from pathlib import Path
from run import save_json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
rows=[]
for seed in (0,1):
 name=f'symbolic-ppo-durable-seed{seed}'
 with (ROOT/'learning-runs/remembered-grid'/f'{name}.log').open('w') as f:
  subprocess.run([str(ROOT/'.venv/bin/python'),str(HERE/'symbolic_ppo.py'),'--mode','detached_critic','--gae-lambda','1','--seed',str(seed),'--name',name,'--decisions','3000000'],stdout=f,stderr=subprocess.STDOUT,check=True)
 r=json.loads((ROOT/'results'/f'{name}.json').read_text());base=r['baseline'];end=r['checkpoints'][-1]['metrics']
 # Prespecified engineering gates, not statistical significance claims.
 checks={}
 for split in ('test_greedy','long_greedy','test_sampled'):
  for kind in ('known_stairs','exploration'):
   checks[split+'/'+kind]=end[split][kind]['exit']>=base[split][kind]['exit']-.05
  checks[split+'/threat']=end[split]['threat_backtrack']['exit']>=.95
 checks['long_known_gain']=end['long_greedy']['known_stairs']['exit']>=base['long_greedy']['known_stairs']['exit']+.05
 rows.append(dict(seed=seed,checks=checks,passed=all(checks.values())))
 save_json(ROOT/'results/symbolic-ppo-durability-gate.json',dict(rows=rows,complete=len(rows)==2,passed=len(rows)==2 and all(x['passed'] for x in rows)))
 print(rows[-1],flush=True)
