"""Observation-only tactical switch, without hindsight selection of a first move."""
import json
import torch
import run

@torch.no_grad()
def main():
    torch.set_num_threads(1)
    data=torch.load(run.SUITE/'snapshots.pt',map_location='cpu',weights_only=False)
    screen=torch.load(run.SUITE/'screen.pt',map_location='cpu',weights_only=False)
    models={'base':run.Policy('d4_exact',128).cuda().eval()}
    models['base'].load_state_dict(torch.load(run.BASE,map_location='cpu',weights_only=False)['model'])
    models['tactical']=run.expand_weights(torch.load(run.TACTICAL,map_location='cpu',weights_only=False)['model']).eval()
    folder=run.SUITE/'early';folder.mkdir(exist_ok=True)
    store=run.Store(folder,2*1024**3,10*1024**3)
    # At this state, replacing future simulator RNG cannot change the current
    # observations. Forcing the controller's own current action is therefore
    # exactly equivalent to simply running that controller from this state.
    selected=[dict(case=i,episode=int(data['ids'][i]),stage=3,controller='tactical',action=int(screen['tactical']['default'][3,i])) for i in range(len(data['ids']))]
    store.json('selection.json',dict(rule='Always switch to the existing tactical policy for visible-awake combat at encounter start; no action/outcome search',cases=selected))
    if (folder/'robustness.pt').exists():
        r=torch.load(folder/'robustness.pt',weights_only=False);accepted,outputs=r['selected'],r['outputs']
    else:accepted,outputs=run.robustness(data,models,selected,store)
    cases=[]
    for i,c in enumerate(accepted):
        base=outputs['base'][i,:,2];other=outputs['witness'][i,:,2]
        cases.append(dict(case=i,episode=c['episode'],base_exit=float(base.mean()),tactical_exit=float(other.mean()),
                          delta=float((other-base).mean()),base_outcomes=base.tolist(),tactical_outcomes=other.tolist()))
    result=dict(method='Same 58 death cases, encounter-start snapshots, 64 fresh simulator RNGs per case, both policies greedy. Tactical switch uses current visible-awake observation, never hidden map or future RNG.',
                base_mean_exit=float(outputs['base'][:,:,2].mean()),tactical_mean_exit=float(outputs['witness'][:,:,2].mean()),
                strong_rescues=sum(c['tactical_exit']>=.75 and c['delta']>=.2 for c in cases),
                improved_cases=sum(c['delta']>0 for c in cases),worse_cases=sum(c['delta']<0 for c in cases),cases=cases)
    store.json('result.json',result)
    (run.ROOT/'results/d1-stairs-deaths-early.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print({k:v for k,v in result.items() if k!='cases'},flush=True)

if __name__=='__main__':main()
