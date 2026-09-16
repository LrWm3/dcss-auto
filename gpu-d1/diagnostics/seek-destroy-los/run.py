"""Compare privileged native seek-and-destroy with saved LOS-policy validation.

Uses each original branch wrapper and verified original evaluation library.
Each worker is a fresh process to avoid same-named module collisions.
"""
import argparse,hashlib,json,pathlib,subprocess,sys
ROOT=pathlib.Path(__file__).resolve().parents[2]
CASES=[
 ('los9-512','vision-awareness-v1','vision24-512-los-awareness-30m','local_los-seed0'),
 ('los15-2048','vision15-train2048-v1','vision15-no-travel-train2048-10m','vision15_no_travel-seed0'),
 ('los15-seen-death4','vision15-seen-death4-30m-v1','vision15-seen-death4-30m','tiles_seen_death4-seed0'),
 ('los15-sleep-wait','vision15-rest-sleep-v1','vision15-rest-sleep','wait-seed0'),
 ('los15-sleep-rest','vision15-rest-sleep-v1','vision15-rest-sleep','rest-seed0'),
]

def worker(index):
 import torch
 torch.set_num_threads(1)
 label,branch,suite,job_id=CASES[index]
 sys.path.insert(0,str(ROOT/'branches'/branch/'scripts'))
 import run_ring_ablations as runner
 from learn_env_ring_multi import Env
 directory=ROOT/'learning-runs'/suite
 manifest=json.loads((directory/'manifest.json').read_text())
 job=next(j for j in manifest['jobs'] if j['id']==job_id)
 lib=pathlib.Path(job['eval_library']) if 'eval_library' in job else directory/'build'/(runner.library_key(job)+'.so')
 digest=hashlib.sha256(lib.read_bytes()).hexdigest()
 assert digest==lib.with_suffix('.sha256').read_text().strip()
 learned=json.loads((directory/'runs'/job_id/'result.json').read_text())
 n=job['validation_maps']*job['eval_per_map'];assert n==1024
 env=Env(n,job['enemies'],seed=900000,corpus=pathlib.Path(manifest['corpus'])/'validation',map_limit=job['validation_maps'],map_filter=-2,library_path=lib,limit=job['turn_limit'])
 metrics={}
 for rest in ([False,True] if job.get('rest_action') else [False]):
  env.reset(900000);active=torch.ones(n,dtype=torch.bool,device='cuda');terminal=torch.zeros_like(env.out)
  decisions=torch.zeros(n,device='cuda');rests=torch.zeros(n,device='cuda');rest_turns=torch.zeros(n,device='cuda')
  for _ in range(job['turn_limit']):
   if not active.any():break
   action=env.heuristic().clone()
   if rest:action=torch.where(env.mask[:,9]>0,9,action)
   assert bool(((env.mask.gather(1,action[:,None]).squeeze(1)>0)|~active).all())
   decisions+=active
   if rest:rests+=active&(action==9)
   env.step(action,active=active)
   if rest:rest_turns+=active*env.out[:,35]
   ended=active&(env.out[:,1]>0);terminal[ended]=env.out[ended];active&=~ended
  assert not bool(active.any())
  clears=terminal[:,2]>0
  metrics['seek_destroy_rest' if rest else 'seek_destroy']=dict(clear_rate=float(clears.float().mean()),kills=float(terminal[:,3].mean()),death_rate=float(terminal[:,6].mean()),timeout_rate=float(terminal[:,7].mean()),turns=float(terminal[:,5].mean()),clear_only_turns=float(terminal[clears,5].mean()),policy_decisions=float(decisions.mean()),rest_uses=float(rests.mean()),rest_turns=float(rest_turns.mean()),episodes=n)
  print(label,rest,metrics['seek_destroy_rest' if rest else 'seek_destroy'],flush=True)
 result=dict(label=label,branch=branch,suite=suite,job=job,library=str(lib),library_sha256=digest,config=list(env.config),map_ids=[m['seed'] for m in env.metadata],map_sha256={m['path']:hashlib.sha256((pathlib.Path(manifest['corpus'])/'validation'/m['path']).read_bytes()).hexdigest() for m in env.metadata},seed=900000,trained_decisions=learned['decisions'],learned_source=str(directory/'runs'/job_id/'result.json'),learned=learned['final'],heuristics=metrics)
 out=ROOT/'results'/f'seek-destroy-{label}.json';out.write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--worker',type=int);args=p.parse_args()
 if args.worker is not None:worker(args.worker)
 else:
  for i in range(len(CASES)):subprocess.run([sys.executable,__file__,'--worker',str(i)],check=True)
