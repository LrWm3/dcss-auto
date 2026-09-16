"""Small PPO/update/resume checks; never used for experimental results."""
import sys,pathlib,subprocess,json
scripts=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(scripts))
from prepare import plan,initialize
from assets import ROOT
import run_ring_ablations as r
m=plan();root=ROOT/'learning-runs/tactical-next-smoke';root.mkdir(parents=True,exist_ok=True);store=r.Store(root,4*r.GIB,10*r.GIB)
jobs=[]
for kind in ['enemy_set','d4_exact','targeted','continue']:
 j=dict(next(j for j in m['jobs'] if j['id']==kind+'_ordinary-seed0'))
 j.update(validation_maps=2,eval_per_map=2,epochs=1)
 if kind in ['targeted','continue']:j.update(steps=30015488+32768)
 else:j.update(steps=256,batch=8,horizon=16,maps=2,minibatch=128)
 jobs.append(j)
m['jobs']=jobs;store.json('manifest.json',m)
for j in jobs:
 initialize(store,j)
 for attempt in range(2):
  subprocess.run([sys.executable,str(scripts/'run_ring_ablations.py'),'--worker',j['id'],'--output',str(root),'--max-disk-gb','4','--min-free-gb','10'],check=True)
print('ALL TRAINING AND RESUME SMOKES PASSED',flush=True)

(ROOT/'results/tactical-next-training-smoke.json').write_text(json.dumps(dict(ppo_and_resume_passed=True,jobs=[j['id'] for j in jobs]),indent=2)+'\n')
