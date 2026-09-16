"""Rule substitutions and paired state continuations for the semantic policy."""
import sys,json,pathlib,time,hashlib,ctypes,subprocess
import numpy as np
import torch
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'branches/semantic-actions-v1/scripts'))
from tactical_models import Policy
from learn_env_ring_multi import Env
from assets import FLAGS

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
@torch.no_grad()
def main():
 torch.set_num_threads(1);torch.distributions.Distribution.set_default_validate_args(False)
 suite=ROOT/'learning-runs/semantic-actions';manifest=json.loads((suite/'manifest.json').read_text());j=manifest['jobs'][0]
 cp=suite/'runs/semantic-seed0/latest.pt';saved=torch.load(cp,map_location='cpu',weights_only=False)
 model=Policy(j['architecture'],j['width']).cuda();model.load_state_dict(saved['model']);model.eval()
 lib=pathlib.Path(j['eval_library']);assert digest(lib)==lib.with_suffix('.sha256').read_text().strip()
 def world(n):return Env(n,24,seed=900000,corpus=pathlib.Path(manifest['corpus'])/'validation',map_limit=32,map_filter=-2,library_path=lib,limit=2048)
 env=world(1024);reference=json.loads((ROOT/'results/semantic-actions-reference.json').read_text())['episodes_detail']
 old=json.loads((ROOT/'results/semantic-actions-rest-override.json').read_text())['results']
 categories={0:'adjacent_attack',3:'awake_wait',2:'sleeper_engage',1:'explore'}
 results={};snapshots={}
 ref_clear=torch.tensor([x['clear'] for x in reference],device='cuda')
 target=torch.tensor([not x['clear'] for x in old['greedy_rest']['episodes']],device='cuda')&ref_clear
 for mode in ['sampled','greedy']:
  for variant,rules in [('rest',[]),('attack',[0]),('awake_wait',[3]),('progress',[1,2]),('attack_wait',[0,3]),('all',[0,1,2,3,4])]:
   key=mode+'_'+variant;env.reset(900000);torch.manual_seed(900000);start=time.monotonic()
   active=torch.ones(1024,device='cuda',dtype=torch.bool);terminal=torch.zeros_like(env.out);counts=torch.zeros(1024,5,device='cuda');changes=torch.zeros(1024,device='cuda');turns=torch.zeros_like(changes)
   # [visits, disagreements, lowHP disagreements, summed visible enemies, summed adjacent enemies]
   stats=torch.zeros(5,5,device='cuda');confusion=torch.zeros(5,5,device='cuda');near=torch.zeros(1024,5,device='cuda');death_near=torch.zeros(5,device='cuda')
   for step in range(2048):
    if not active.any():break
    dist,_=model(env.obs,env.mask);raw=dist.sample() if mode=='sampled' else dist.probs.argmax(-1)
    a=torch.where(env.mask[:,4]>0,4,raw);h=env.heuristic().clone()
    if variant=='rest':
     enemies=env.obs[:,450:650].reshape(-1,40,5);visible=(enemies[:,:,4]>0)
     adjacent=visible&(enemies[:,:,0].abs()<=1.001/80)&(enemies[:,:,1].abs()<=1.001/70)
     for cat in categories:
      visit=active&(h==cat);diff=visit&(a!=h)
      stats[cat,0]+=visit.sum();stats[cat,1]+=diff.sum();stats[cat,2]+=(diff&(env.obs[:,650]<.5)).sum()
      stats[cat,3]+=(diff*visible.sum(1)).sum();stats[cat,4]+=(diff*adjacent.sum(1)).sum()
      near[:,cat]=torch.where(diff,torch.full_like(near[:,cat],step+1),near[:,cat])
     confusion.index_put_((h[active],a[active]),torch.ones_like(a[active],dtype=torch.float),accumulate=True)
     if mode=='greedy':
      ids=torch.where(target&active&(a!=h)&(h!=4))[0].tolist()
      for i in ids:
       cat=int(h[i]);k=(i,cat);entry=dict(episode=i,category=categories[cat],decision=step,model_action=int(a[i]),reference_action=cat,hp=float(env.obs[i,650]*18),visible=int(visible[i].sum()),adjacent=int(adjacent[i].sum()),state=env.state[i].cpu().clone(),obs=env.obs[i].cpu().clone(),mask=env.mask[i].cpu().clone())
       if k not in snapshots:snapshots[k]={'first':entry}
       snapshots[k]['last']=entry
    for rule in rules:a=torch.where(h==rule,h,a)
    if variant=='all':assert torch.equal(a[active],h[active])
    changes+=active&(a!=raw);counts.scatter_add_(1,a[:,None],active.float()[:,None]);env.step(a,active=active);turns+=active*env.out[:,26]
    ended=active&(env.out[:,1]>0);terminal[ended]=env.out[ended]
    deaths=ended&(env.out[:,6]>0)
    death_near+=((near>0)&((step+1-near)<=10)&deaths[:,None]).sum(0)
    active&=~ended
   assert not active.any();assert torch.equal(turns,terminal[:,5]);t=terminal.cpu()
   episodes=[dict(clear=bool(row[2]),death=bool(row[6]),timeout=bool(row[7]),kills=int(row[3]),turns=int(row[5])) for row in t]
   if variant=='rest':assert episodes==old[mode+'_rest']['episodes']
   if variant=='all':
    for x,y in zip(episodes,reference):
     for field,rf in [('clear','clear'),('death','death'),('timeout','timeout'),('kills','kills'),('turns','physical_turns')]:assert x[field]==y[rf],(key,field,x,y)
   baseline=old[mode+'_rest']['episodes']
   metrics=dict(clears=int(t[:,2].sum()),deaths=int(t[:,6].sum()),timeouts=int(t[:,7].sum()),turns=float(turns.mean()),actions={name:float(counts[:,k].mean()) for k,name in enumerate(['attack','explore','engage','wait','rest'])},gained_vs_rest=sum(not x['clear'] and y['clear'] for x,y in zip(baseline,episodes)),lost_vs_rest=sum(x['clear'] and not y['clear'] for x,y in zip(baseline,episodes)),reference_only=sum(y['clear'] and not x['clear'] for x,y in zip(episodes,reference)),model_only=sum(x['clear'] and not y['clear'] for x,y in zip(episodes,reference)),seconds=time.monotonic()-start)
   results[key]=dict(metrics=metrics,episodes=episodes)
   if variant=='rest':results[key].update(disagreements={name:dict(zip(['visits','disagreements','below_half_hp','visible_enemy_sum','adjacent_enemy_sum'],stats[k].cpu().tolist())) for k,name in categories.items()},reference_by_model_action_counts=confusion.cpu().tolist(),deaths_with_disagreement_in_last_10_decisions={name:int(death_near[k]) for k,name in categories.items()})
   print(key,json.dumps(metrics),flush=True)
 out=ROOT/'results/semantic-actions-rule-ablation.json'
 report=dict(checkpoint_sha256=digest(cp),library_sha256=digest(lib),script_sha256=digest(pathlib.Path(__file__)),results=results)
 out.write_text(json.dumps(report,indent=2)+'\n')
 # Pick up to three distinct failure episodes per rule; last disagreement in each.
 selected=[]
 for cat in categories:
  candidates=[v['last'] for (i,c),v in sorted(snapshots.items()) if c==cat]
  selected+=candidates[:3]
 artifacts=ROOT/'learning-runs/semantic-rule-audit';artifacts.mkdir(exist_ok=True)
 torch.save(selected,artifacts/'states.pt')
 # Query native offsetof rather than assume ABI layout for the RNG state.
 source=artifacts/'rng_offset.cu';source.write_text('#include <cstddef>\n#include "'+str(ROOT/'branches/semantic-actions-v1/src/learn.cu')+'"\nextern "C" int rng_offset(){return offsetof(State,w)+offsetof(World,rng)+offsetof(sim::RNG,state);}\n')
 helper=artifacts/'rng-offset.so';subprocess.run(['nvcc','-O3','-std=c++17','-arch=sm_75','-ccbin','/usr/bin/g++-12','-shared','-Xcompiler','-fPIC',*FLAGS,'-DCLUMP_MODE=0',str(source),'-o',str(helper)],check=True)
 native=ctypes.CDLL(str(helper));offset=native.rng_offset();assert native.learn_state_bytes()==env.state.shape[1]
 # Each alternative shares initial state and RNG. Draw 16 additional RNG states;
 # retain repeat 0 as the exact saved episode continuation. Continue greedily + rest.
 repeats=17;n=len(selected)*repeats*2;replay=world(n);rng=np.random.default_rng(7341)
 for case,e in enumerate(selected):
  for rep in range(repeats):
   state=e['state'].clone()
   if rep:state[offset:offset+8]=torch.from_numpy(rng.bytes(8) and np.frombuffer(rng.bytes(8),dtype=np.uint8).copy())
   for branch in range(2):
    row=(case*repeats+rep)*2+branch;replay.state[row].copy_(state);replay.obs[row].copy_(e['obs']);replay.mask[row].copy_(e['mask'])
 assert torch.equal(replay.state[::2],replay.state[1::2])
 first=torch.tensor([a for e in selected for rep in range(repeats) for a in [e['model_action'],e['reference_action']]],device='cuda')
 active=torch.ones(n,device='cuda',dtype=torch.bool);terminal=torch.zeros_like(replay.out)
 for step in range(2048):
  if not active.any():break
  if step==0:a=first
  else:
   dist,_=model(replay.obs,replay.mask);a=dist.probs.argmax(-1);a=torch.where(replay.mask[:,4]>0,4,a)
  assert bool(((replay.mask.gather(1,a[:,None]).squeeze(1)>0)|~active).all())
  replay.step(a,active=active);ended=active&(replay.out[:,1]>0);terminal[ended]=replay.out[ended];active&=~ended
 assert not active.any();t=terminal.cpu().reshape(len(selected),repeats,2,-1);details=[]
 for k,e in enumerate(selected):
  assert not bool(t[k,0,0,2]),'Exact baseline continuation must reproduce selected failure'
  details.append(dict(**{key:v for key,v in e.items() if key not in ['state','obs','mask']},original=[dict(clear=bool(row[2]),death=bool(row[6]),timeout=bool(row[7]),turns=int(row[5])) for row in t[k,0]],randomized_future_clears=[int(t[k,1:,b,2].sum()) for b in range(2)],randomized_reference_only=int(((t[k,1:,0,2]==0)&(t[k,1:,1,2]>0)).sum()),randomized_model_only=int(((t[k,1:,0,2]>0)&(t[k,1:,1,2]==0)).sum())))
 report['replays']=dict(selection='Last disagreement, first three reference-only failed greedy episodes per rule (overlap allowed). Selected diagnostic cases, not an unbiased estimate.',continuation='Identical greedy policy with forced rest after one substituted action',randomized_repeats=16,rng_offset=offset,cases=details)
 out.write_text(json.dumps(report,indent=2)+'\n');print('REPLAYS',json.dumps(details),flush=True)
if __name__=='__main__':main()
