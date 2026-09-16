"""Test first-update causal interventions in the original streaming PPO runner."""
import json,pathlib,subprocess,sys,time,fcntl
import episode_credit as ec
ROOT=ec.ROOT
import run_ring_ablations as runner

def main():
 if '--worker' in sys.argv:
  import tactical_models
  original=tactical_models.Policy
  if '--freeze-body' in sys.argv:
   sys.argv.remove('--freeze-body')
   def policy(*a,**kw):
    model=original(*a,**kw)
    for p in model.body[0].parameters():p.requires_grad_(False)
    return model
   tactical_models.Policy=policy
  return runner.main()
 suite=ROOT/'learning-runs/autoregressive-update-prevention';suite.mkdir(exist_ok=True);store=runner.Store(suite,2*runner.GIB,10*runner.GIB)
 with (suite/'.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  old=json.loads((ROOT/'learning-runs/autoregressive-turn-cost/manifest.json').read_text());base=old['jobs'][0]
  jobs=[dict(base,id='frozen-first-layer-seed0',name='frozen-first-layer',freeze_body=True),dict(base,id='lr10-seed0',name='lr10',lr=.00003),dict(base,id='drop-negative-move-seed0',name='drop-negative-move',diagnostic_drop_negative_move_advantage=True)]
  m=dict(corpus=old['corpus'],jobs=jobs,script_sha256=runner.digest(pathlib.Path(__file__)),control='autoregressive-turn-cost');store.json('manifest.json',m);start=time.monotonic();result={}
  for job in jobs:
   store.json('status.json',dict(status='running',job=job['id']))
   cmd=[sys.executable,__file__,'--worker',job['id'],'--output',str(suite),'--max-disk-gb','2','--min-free-gb','10']
   if job.get('freeze_body'):cmd+=['--freeze-body']
   subprocess.run(cmd,check=True)
   r=json.loads((suite/'runs'/job['id']/'result.json').read_text());result[job['id']]=dict(ppo=r,evaluations=json.loads((suite/'runs'/job['id']/'curve.json').read_text()))
   (ROOT/'results/autoregressive-update-prevention.json').write_text(json.dumps(result,indent=2)+'\n')
  store.json('status.json',dict(status='complete',seconds=time.monotonic()-start))
if __name__=='__main__':main()
