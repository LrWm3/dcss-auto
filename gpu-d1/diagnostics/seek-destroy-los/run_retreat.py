"""Matched 2x2 evaluation: local/privileged pursuit × hallway retreat on/off."""
import argparse,hashlib,json,pathlib,sys,time
import torch
from retreat_policy import RetreatPolicy,EVENTS,ROOT
sys.path.insert(0,str(ROOT/'branches/vision15-rest-sleep-v1/scripts'))
from learn_env_ring_multi import Env

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--wait-for-awake',action='store_true');args=parser.parse_args()
 torch.set_num_threads(1);suite=ROOT/'learning-runs/vision15-rest-sleep'
 manifest=json.loads((suite/'manifest.json').read_text());job=next(j for j in manifest['jobs'] if j['id']=='rest-seed0')
 lib=pathlib.Path(job['eval_library']);digest=hashlib.sha256(lib.read_bytes()).hexdigest();assert digest==lib.with_suffix('.sha256').read_text().strip()
 env=Env(1024,24,seed=900000,corpus=pathlib.Path(manifest['corpus'])/'validation',map_limit=32,map_filter=-2,library_path=lib,limit=2048)
 results={};start=time.monotonic()
 for privileged in (True,False):
  for retreat in (False,True):
   name=('privileged' if privileged else 'local')+('-retreat' if retreat else '-control')
   env.reset(900000);policy=RetreatPolicy(env,privileged,retreat,wait_for_awake=args.wait_for_awake)
   active=torch.ones(1024,dtype=torch.bool,device='cuda');terminal=torch.zeros_like(env.out)
   totals=torch.zeros((1024,len(EVENTS)),device='cuda');decisions=torch.zeros(1024,device='cuda');rests=torch.zeros_like(decisions);rest_turns=torch.zeros_like(decisions)
   approach_waits=torch.zeros_like(decisions)
   death_retreat=torch.zeros_like(active);death_hold=torch.zeros_like(active)
   for turn in range(2048):
    if not active.any():break
    action=policy(active)
    assert bool(((env.mask.gather(1,action[:,None]).squeeze(1)>0)|~active).all())
    approach_waits+=policy.approach_wait
    decisions+=active;rests+=(action==9)&active
    env.step(action,active=active)
    ended=active&(env.out[:,1]>0);policy.after_step(ended)
    totals+=policy.events*active[:,None];rest_turns+=env.out[:,35]*active
    death_retreat|=ended&(env.out[:,6]>0)&(policy.events[:,4]>0)
    death_hold|=ended&(env.out[:,6]>0)&(policy.events[:,3]>0)
    terminal[ended]=env.out[ended];active&=~ended
   assert not bool(active.any())
   clear=terminal[:,2]>0;triggered=totals[:,0]>0
   metric=dict(approach_waits=float(approach_waits.mean()),clear_rate=float(clear.float().mean()),death_rate=float(terminal[:,6].mean()),timeout_rate=float(terminal[:,7].mean()),kills=float(terminal[:,3].mean()),turns=float(terminal[:,5].mean()),clear_only_turns=float(terminal[clear,5].mean()),policy_decisions=float(decisions.mean()),rest_uses=float(rests.mean()),rest_turns=float(rest_turns.mean()),retreat_episode_rate=float(triggered.float().mean()),death_on_retreat_action_rate=float(death_retreat.float().mean()),death_on_hold_wait_rate=float(death_hold.float().mean()),events_per_episode={key:float(totals[:,i].mean()) for i,key in enumerate(EVENTS)})
   if not retreat and not args.wait_for_awake:
    old=json.loads((ROOT/'results'/f"{'seek' if privileged else 'local'}-destroy-los15-sleep-rest.json").read_text())['heuristics']['seek_destroy_rest']
    for key in ['clear_rate','death_rate','timeout_rate','kills','turns','rest_uses']:assert metric[key]==old[key],(name,key,metric[key],old[key])
   result=dict(metrics=metric,episodes=[dict(map_seed=env.metadata[i%32]['seed'],clear=bool(clear[i]),death=bool(terminal[i,6]),timeout=bool(terminal[i,7]),kills=int(terminal[i,3]),turns=int(terminal[i,5]),retreat_events=totals[i].int().tolist()) for i in range(1024)])
   results[name]=result;print(name,json.dumps(metric),flush=True)
 for base in ['privileged','local']:
  a=results[base+'-control']['episodes'];b=results[base+'-retreat']['episodes']
  results[base+'-retreat']['paired_clear_outcomes']=dict(both_clear=sum(x['clear'] and y['clear'] for x,y in zip(a,b)),retreat_only_clear=sum(not x['clear'] and y['clear'] for x,y in zip(a,b)),control_only_clear=sum(x['clear'] and not y['clear'] for x,y in zip(a,b)),neither_clear=sum(not x['clear'] and not y['clear'] for x,y in zip(a,b)))
 report=dict(wait_for_awake=args.wait_for_awake,episodes_per_arm=1024,validation_maps=32,seed=900000,budget='2048 policy decisions',enemies=24,vision='15x15 wall-blocked, LOS-gated waking',rest_rule='below full HP and no visible enemy (sleepers block)',job=job,library_sha256=digest,config=list(env.config),policy_sha256={f:hashlib.sha256(pathlib.Path(__file__).with_name(f).read_bytes()).hexdigest() for f in ['local_policy.cu','retreat_policy.cu','retreat_policy.py','run_retreat.py']},events_order=EVENTS,results=results,wall_seconds=time.monotonic()-start)
 (ROOT/('results/los-hallway-wait-awake.json' if args.wait_for_awake else 'results/los-hallway-retreat.json')).write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':main()
