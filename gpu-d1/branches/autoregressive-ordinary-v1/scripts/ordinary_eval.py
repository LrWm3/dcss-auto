"""Full-floor outcomes and observation-only combat counterfactuals."""
import argparse,json,pathlib,time
import torch
from tactical_models import Policy
from learn_env_ring_multi import Env
ROOT=pathlib.Path(__file__).resolve().parents[3]
SOURCE=ROOT/'learning-runs/autoregressive-survival/runs/exploration-seed0/latest.pt'
DXY=[(0,-1),(1,0),(0,1),(-1,0),(1,-1),(1,1),(-1,1),(-1,-1)]

def combat_labels(obs,mask):
    adjacent=mask[:,8:16]>0
    inds=[225+(7+y)*15+7+x for x,y in DXY]
    hp=obs[:,inds].masked_fill(~adjacent,float('inf'))
    attack=8+hp.argmin(1);has_adj=adjacent.any(1)
    awake=(obs[:,959:999]<0).any(1)
    label=torch.where(has_adj,attack,16)
    return label,has_adj,awake

@torch.no_grad()
def evaluate(model,job,corpus,seed=900000,batch=1024,mode='greedy',override='none',map_limit=32,split='validation'):
    env=Env(batch,24,seed=seed,corpus=pathlib.Path(corpus)/split,map_limit=map_limit,map_filter=-2,library_path=job['eval_library'],limit=2048)
    active=torch.ones(batch,dtype=torch.bool,device='cuda');terminal=torch.zeros_like(env.out);ret=torch.zeros(batch,device='cuda')
    last=torch.zeros(batch,7,device='cuda');stats=torch.zeros(batch,5,device='cuda');prev=torch.full((batch,2),-100.,device='cuda');streak=torch.zeros(batch,device='cuda');maxloop=streak.clone()
    with torch.random.fork_rng(devices=[0]):
        torch.manual_seed(seed)
        for step in range(2048):
            label,adj,awake=combat_labels(env.obs,env.mask)
            dist,_=model(env.obs,env.mask);a=dist.greedy() if mode=='greedy' else dist.sample()
            if override=='attack':a=torch.where(adj,label,a)
            if override=='wait':a=torch.where(awake&~adj,16,a)
            if override=='combat':a=torch.where(adj|awake,label,a)
            if override=='combat_rest':a=torch.where(adj|awake,label,torch.where(env.mask[:,17]>0,17,a))
            if override in ['teacher','navigation']:
                teacher=env.heuristic().clone()
                a=teacher if override=='teacher' else torch.where(~awake,teacher,a)
            assert ((env.mask.gather(1,a[:,None]).squeeze(1)>0)|~active).all()
            xy=env.obs[:,652:654].clone();n_adj=(env.mask[:,8:16]>0).sum(1);n_awake=(env.obs[:,959:999]<0).sum(1)
            last=torch.where(active[:,None],torch.stack([env.obs[:,650]*18,n_adj,n_awake,a,env.obs[:,958],env.obs[:,725:733].argmax(1),env.mask[:,17]],1),last)
            stats+=torch.stack([awake&~adj&(a<8),adj&(a<8),adj&(a==16),adj&(a>=8)&(a<16)&(a!=label),n_adj>1],1)*active[:,None]
            env.step(a,active=active);ret+=active*env.out[:,40];done=active&(env.out[:,1]>0)
            reverse=active&~done&(a<8)&(env.obs[:,652:654]==prev).all(1)&(xy!=prev).any(1)
            streak=torch.where(reverse,streak+1,0);maxloop=torch.maximum(maxloop,streak);prev=xy
            terminal[done]=env.out[done];active&=~done
            if not active.any():break
    assert not active.any();torch.testing.assert_close(ret,terminal[:,2]-.00001*terminal[:,5],atol=1e-4,rtol=0)
    t=terminal.cpu();s=stats.cpu();last=last.cpu();loops=maxloop.cpu();dead=t[:,6]>0;timeout=t[:,7]>0
    out=dict(seed=seed,batch=batch,mode=mode,override=override,clear=float(t[:,2].mean()),death=float(t[:,6].mean()),timeout=float(t[:,7].mean()),turns=float(t[:,5].mean()),reward=float(ret.mean()),loop_timeouts=int((timeout&(loops>=8)).sum()),behavior={name:float(s[:,i].mean()) for i,name in enumerate(['moves_toward_visible_combat','moves_while_adjacent','waits_while_adjacent','nonweakest_attacks','multi_adjacent_turns'])},deaths=[dict(episode=i,map_seed=env.metadata[i%map_limit]['seed'],turns=float(t[i,5]),kills=float(t[i,3]),last=dict(zip(['hp','adjacent','awake','action','seen_fraction','frontier_direction','rest_available'],last[i].tolist())),behavior=s[i].tolist()) for i in torch.where(dead)[0].tolist()],episodes=dict(clear=t[:,2].tolist(),death=t[:,6].tolist(),timeout=t[:,7].tolist(),turns=t[:,5].tolist()),maps=[int(m['seed']) for m in env.metadata])
    return out

def main():
    torch.set_num_threads(1);start=time.monotonic();c=torch.load(SOURCE,map_location='cpu',weights_only=False)
    corpus=json.loads((ROOT/'learning-runs/autoregressive-survival/manifest.json').read_text())['corpus']
    model=Policy('d4_exact',128).cuda().eval();model.load_state_dict(c['model']);results={}
    # Native/observation label agreement on states actually visited by the model.
    env=Env(64,24,seed=71235,corpus=pathlib.Path(corpus)/'train',map_limit=256,library_path=c['job']['train_library'])
    for _ in range(64):
        labels,adj,awake=combat_labels(env.obs,env.mask);h=env.heuristic().clone();eligible=adj|awake
        assert torch.equal(labels[eligible],h[eligible])
        with torch.no_grad():env.step(model(env.obs,env.mask)[0].sample())
    for mode,override in [('sampled','none'),('greedy','none'),('greedy','attack'),('greedy','wait'),('greedy','combat'),('sampled','combat')]:
        key=mode+'_'+override;results[key]=evaluate(model,c['job'],corpus,mode=mode,override=override)
        print(key,{k:results[key][k] for k in ['clear','death','timeout','turns','loop_timeouts']},flush=True)
        (ROOT/'results/autoregressive-ordinary-diagnosis.json').write_text(json.dumps(dict(source=str(SOURCE),results=results,wall_seconds=time.monotonic()-start),indent=2,allow_nan=False)+'\n')

if __name__=='__main__':main()
