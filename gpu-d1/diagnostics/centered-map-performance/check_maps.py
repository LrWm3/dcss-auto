import json,os,pathlib,signal,sys,time
import torch
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'branches/vision15-centered-map-v1/scripts'))
from tactical_models import Policy
from fast_maps import spatial
pid=int(sys.argv[1]) if len(sys.argv)>1 else None
if pid:os.kill(pid,signal.SIGSTOP)
try:
 torch.set_num_threads(1)
 saved=torch.load(ROOT/'learning-runs/centered-map-smoke/runs/rest-seed0/latest.pt',map_location='cpu',weights_only=False)
 obs=saved['env_obs'][:32].cuda();model=Policy().cuda()
 # Valid synthetic observations at all four corners exercise maximal displacements.
 for b,(x,y) in enumerate([(0,0),(79,0),(0,69),(79,69)]):
  obs[b,652:654]=torch.tensor([x/80,y/70],device='cuda')
  obs[b,450:650]=0;obs[b,959:999]=0
  for j,(mx,my) in enumerate([(0,0),(79,0),(0,69),(79,69)]):
   obs[b,450+j*5:455+j*5]=torch.tensor([(mx-x)/80,(my-y)/70,(j+1)/16,.6,1],device='cuda');obs[b,959+j]=1 if j%2 else -1
 with torch.no_grad():
  maps=model.centered(obs);variants=[]
  for g in range(8):variants.append(torch.rot90(maps.flip(-1) if g//4 else maps,-(g%4),(-2,-1)))
  expected=torch.nn.functional.pad(torch.cat(variants),(0,1,0,1))
  actual=spatial(obs);torch.testing.assert_close(actual,expected,atol=0,rtol=0)
  half=spatial(obs,torch.float16);torch.testing.assert_close(half.float(),expected,atol=0,rtol=0)
 print('Fused map equals original exactly, including corners, all 8 transforms, HP, sleep, and padding.',flush=True)
finally:
 if pid:os.kill(pid,signal.SIGCONT)
