"""Check whether the ordinary-floor intervention sacrifices prior tactical skills."""
import json,pathlib,sys,torch
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'branches/autoregressive-survival-targeted-v2/scripts'))
from tactical_models import Policy
from survival_eval import evaluate_tactics

torch.set_num_threads(1)
selection=json.loads((ROOT/'learning-runs/autoregressive-ordinary/selection.json').read_text())
paths={'source':ROOT/'learning-runs/autoregressive-survival/runs/exploration-seed0/latest.pt','ordinary_candidate':pathlib.Path(selection['checkpoints']['selected']['path']),'balanced_tactics':ROOT/'learning-runs/autoregressive-survival-balanced/runs/balanced-seed0/latest.pt'}
job={'tactical_library':str(ROOT/'learning-runs/autoregressive-survival-assets/survival.so')};results={}
for name,path in paths.items():
 model=Policy('d4_exact',128).cuda().eval();model.load_state_dict(torch.load(path,map_location='cpu',weights_only=False)['model']);results[name]={}
 for panel,folder in [('original','autoregressive-survival-assets'),('far','autoregressive-survival-balanced-assets')]:
  job['tactical_eval_corpus']=str(ROOT/'learning-runs'/folder/'heldout')
  results[name][panel]=evaluate_tactics(model,job)
  print(name,panel,{m:r['overall']['clear'] for m,r in results[name][panel].items()},flush=True)
(ROOT/'results/autoregressive-ordinary-tactical-regression.json').write_text(json.dumps(dict(checkpoints={k:str(v) for k,v in paths.items()},results=results),indent=2,allow_nan=False)+'\n')
