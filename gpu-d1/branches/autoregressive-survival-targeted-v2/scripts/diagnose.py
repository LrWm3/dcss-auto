"""Paired policy/cover rollouts; keep compact, reproducible failure trajectories."""
import argparse,json,pathlib
import torch
from tactical_env import TacticalEnv
from tactical_models import Policy
from scenarios import ROOT,FAMILIES

@torch.no_grad()
def diagnose(checkpoint,corpus,library,seed=830001):
    model=Policy('d4_exact',128).cuda().eval()
    model.load_state_dict(torch.load(checkpoint,map_location='cpu',weights_only=False)['model'])
    env=TacticalEnv(512,24,seed=seed,corpus=pathlib.Path(corpus),map_limit=64,map_filter=-2,library_path=str(library))
    goals=torch.tensor([(35+s['goal'][1])*80+40+s['goal'][0] for s in env.specs],device='cuda').repeat(8)
    results={};traces={}
    for mode in ['policy','cover']:
        env.reset(seed);active=torch.ones(512,dtype=torch.bool,device='cuda')
        end=torch.zeros_like(env.out);reached=torch.zeros_like(active)
        closest=torch.full((512,),100.,device='cuda');last=closest.clone()
        trace=[];initial=None
        for step in range(2048):
            script,st=env.probe(1);stats=st.clone()
            if initial is None:initial=stats.cpu().tolist()
            actions=model(env.obs,env.mask)[0].greedy() if mode=='policy' else script.clone()
            distance=torch.maximum((stats[:,1]%80-goals%80).abs(),(stats[:,1]//80-goals//80).abs())
            closest=torch.where(active,torch.minimum(closest,distance),closest)
            last=torch.where(active,distance,last);reached|=active&stats[:,5].bool()
            trace.append(torch.cat([active[:,None],stats,actions[:,None]],1).cpu().tolist())
            env.step(actions,active=active);done=active&(env.out[:,1]>0);end[done]=env.out[done];active&=~done
            if not active.any():break
        assert not active.any()
        results[mode]=dict(clear=end[:,2].cpu().tolist(),turns=end[:,5].cpu().tolist(),death=end[:,6].cpu().tolist(),reached=reached.cpu().tolist(),closest=closest.cpu().tolist(),last=last.cpu().tolist(),initial=initial)
        traces[mode]=trace
    p,c=results['policy'],results['cover'];groups={};examples=[]
    for f,name in enumerate(FAMILIES):
        ids=[i for i,x in enumerate(p['initial']) if x[7]==f]
        failed=[i for i in ids if p['death'][i]]
        rescued=[i for i in failed if c['clear'][i]]
        groups[name]=dict(episodes=len(ids),policy_clears=sum(p['clear'][i] for i in ids),cover_clears=sum(c['clear'][i] for i in ids),deaths=len(failed),rescued_by_cover=len(rescued),died_after_reaching_cover=sum(p['reached'][i] for i in failed),failed_minimum_distance={str(d):sum(p['closest'][i]==d for i in failed) for d in range(8)},deaths_by_initial_hp={str(h):sum(p['initial'][i][0]==h for i in failed) for h in [6,12,18]})
        for i in rescued[:2]:
            examples.append(dict(episode=i,map_index=i%64,scenario=env.specs[i%64],policy=[t[i][1:] for t in traces['policy'] if t[i][0]],cover=[t[i][1:] for t in traces['cover'] if t[i][0]]))
    return dict(checkpoint=str(checkpoint),corpus=str(corpus),seed=seed,groups=groups,episodes=results,examples=examples,trace_columns=['hp','player_tile','adjacent','visible_awake','ticks','at_cover','alive','family','action'])

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--checkpoint',default=str(ROOT/'learning-runs/autoregressive-survival/runs/exploration-seed0/latest.pt'));ap.add_argument('--corpus',default=str(ROOT/'learning-runs/autoregressive-survival-assets/heldout'));ap.add_argument('--library',default=str(ROOT/'learning-runs/autoregressive-survival-assets/survival.so'));ap.add_argument('--output',default=str(ROOT/'results/autoregressive-survival-failures.json'));a=ap.parse_args()
    torch.set_num_threads(1)
    result=diagnose(a.checkpoint,a.corpus,a.library)
    pathlib.Path(a.output).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result['groups'],indent=2),flush=True)
