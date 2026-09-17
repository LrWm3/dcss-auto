import json,time,torch
from ordinary_eval import *
torch.set_num_threads(1);c=torch.load(SOURCE,map_location='cpu',weights_only=False);model=Policy('d4_exact',128).cuda().eval();model.load_state_dict(c['model']);corpus=json.loads((ROOT/'learning-runs/autoregressive-survival/manifest.json').read_text())['corpus'];start=time.monotonic();results={}
for override in ['navigation','teacher']:
 results[override]=evaluate(model,c['job'],corpus,override=override)
 print(override,{k:results[override][k] for k in ['clear','death','timeout','turns']},flush=True)
 (ROOT/'results/autoregressive-ordinary-teacher-audit.json').write_text(json.dumps(dict(results=results,wall_seconds=time.monotonic()-start),indent=2,allow_nan=False)+'\n')
