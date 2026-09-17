"""Measure parameter and function changes on a fixed training-only probe."""
import json,pathlib,torch
import episode_credit as ec
from tactical_models import Policy
from symmetry import D4
ROOT=ec.ROOT
@torch.no_grad()
def main():
    torch.set_num_threads(1);torch.manual_seed(7812)
    base=torch.load(ROOT/'learning-runs/autoregressive-imitation/imitation.pt',map_location='cpu',weights_only=False)['model']
    ref=Policy('d4_exact',128);ref.load_state_dict(base)
    data=torch.load(ROOT/'learning-runs/autoregressive-anchor-buffer.pt',map_location='cpu',weights_only=False)
    ids=torch.randperm(len(data['obs']))[:512];x=data['obs'][ids];mask=data['mask'][ids];del data
    rotated=D4('cpu').observation(x,torch.randint(8,(len(x),)))
    target=ref(x,mask)[0].probs;features=ref.body[:2](rotated);out={}
    for suite in sorted((ROOT/'learning-runs').glob('autoregressive-anchor-*')):
        if not suite.is_dir():continue
        for cp in sorted(suite.glob('runs/*/snapshots/000010000384.pt')):
            state=torch.load(cp,map_location='cpu',weights_only=False)['model'];model=Policy('d4_exact',128);model.load_state_dict(state)
            p=model(x,mask)[0].probs
            delta={prefix:sum(float((state[k]-v).square().sum()) for k,v in base.items() if k.startswith(prefix))**.5 for prefix in ['body.0.','body.2.','actor.','direction.','critic.']}
            out[cp.parent.parent.name]=dict(layer_parameter_l2_change=delta,first_layer_feature_mse=float((model.body[:2](rotated)-features).square().mean()),joint_policy_kl=float((target*(target.clamp_min(1e-30).log()-p.clamp_min(1e-30).log())).sum(-1).mean()),checkpoint=str(cp))
    (ROOT/'results/autoregressive-anchor-drift.json').write_text(json.dumps(dict(probe='512 fixed training-buffer observations; no validation or test states',results=out),indent=2)+'\n')
    print(json.dumps(out,indent=2))
if __name__=='__main__':main()
