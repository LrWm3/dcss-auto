"""Shared frozen-state comparisons and distinct held-out tactical layouts."""
import json
import pathlib
import sys
import torch
from tactical_models import Policy
from symmetry import D4
from tactical_env import TacticalEnv
from assets import ROOT,ASSETS
import run_ring_ablations as runner

@torch.no_grad()
def frozen(model,bank):
    d=D4();rows=[]
    for start in range(0,len(bank['obs']),256):
        obs=bank['obs'][start:start+256].cuda();mask=bank['mask'][start:start+256].cuda();n=len(obs)
        p,v=model(obs,mask);probs=p.probs
        wait=[];tv=[]
        for g in range(8):
            groups=torch.full((n,),g,device='cuda',dtype=torch.long)
            q,_=model(d.observation(obs,groups),d.mask(mask,groups));canonical=q.probs.gather(1,d.forward[groups])
            wait.append(canonical[:,8]);tv.append((canonical-probs).abs().sum(1)/2)
        permuted=obs.clone();permuted[:,450:650]=obs[:,450:650].reshape(n,40,5).flip(1).flatten(1)
        q,_=model(permuted,mask)
        values=torch.stack([probs[:,8],torch.stack(wait).max(0).values-torch.stack(wait).min(0).values,torch.stack(tv).max(0).values,(q.probs-probs).abs().sum(1)/2,(q.probs[:,8]-probs[:,8]).abs()],1)
        rows.extend(values.cpu().tolist())
    values=torch.tensor(rows)
    phases=sorted({x['phase'] for x in bank['metadata']});summary={}
    for phase in phases+['all']:
        chosen=torch.tensor([phase=='all' or x['phase']==phase for x in bank['metadata']]);a=values[chosen]
        summary[phase]=dict(states=len(a),mean_wait=float(a[:,0].mean()),mean_rotation_wait_range=float(a[:,1].mean()),max_rotation_wait_range=float(a[:,1].max()),mean_rotation_action_tv=float(a[:,2].mean()),max_rotation_action_tv=float(a[:,2].max()),mean_enemy_permutation_action_tv=float(a[:,3].mean()),max_enemy_permutation_action_tv=float(a[:,3].max()),mean_enemy_permutation_wait_delta=float(a[:,4].mean()))
    if model.architecture=='enemy_set':assert summary['all']['max_enemy_permutation_action_tv']<1e-5
    if model.architecture=='d4_exact':assert summary['all']['max_rotation_action_tv']<1e-5
    return dict(bank_sha256=runner.digest(ASSETS/'frozen.pt'),summary=summary,per_state=rows)

@torch.no_grad()
def heldout(model):
    env=TacticalEnv(32*16,24,seed=910000,corpus=ASSETS/'heldout',map_limit=32,map_filter=-2,library_path=ASSETS/'tactical.so')
    active=torch.ones(env.batch,dtype=torch.bool,device='cuda');out=torch.zeros_like(env.out);turns=torch.zeros(env.batch,device='cuda')
    torch.manual_seed(910000)
    for _ in range(512):
        dist,_=model(env.obs,env.mask);env.step(dist.sample(),active=active);turns+=active
        ended=active&(env.out[:,1]>0);out[ended]=env.out[ended];active &= ~ended
        if not active.any():break
    def metrics(ix):return dict(clear=float(out[ix,2].mean()),death=float(out[ix,6].mean()),unresolved=float(active[ix].float().mean()),actions=float(turns[ix].mean()))
    return dict(episodes=env.batch,cap=512,aggregate=metrics(slice(None)),layouts={str(i):metrics(torch.arange(i,env.batch,32,device='cuda')) for i in range(32)})

def main():
    path=pathlib.Path(sys.argv[1]);output=pathlib.Path(sys.argv[2]);torch.set_num_threads(1);torch.backends.cuda.matmul.allow_tf32=False
    checkpoint=torch.load(path,map_location='cpu',weights_only=False)
    architecture=checkpoint['job'].get('architecture','mlp');model=Policy(architecture,checkpoint['job']['width']).cuda().eval();model.load_state_dict(checkpoint['model'])
    bank=torch.load(ASSETS/'frozen.pt',map_location='cpu',weights_only=False)
    report=dict(checkpoint_sha256=runner.digest(path),architecture=architecture,decisions=checkpoint['decisions'],frozen=frozen(model,bank),heldout=heldout(model))
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,separators=(',',':'))+'\n')
    print('Extra evaluation complete',path,report['heldout']['aggregate'],flush=True)
if __name__=='__main__':main()
