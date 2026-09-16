"""Profile precision/layout choices without changing observations or architecture."""
import argparse,contextlib,json,os,pathlib,signal,sys,time
import torch
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'branches/vision15-centered-map-v1/scripts'))
from tactical_models import Policy
p=argparse.ArgumentParser();p.add_argument('--pause-pid',type=int);p.add_argument('--batch',type=int,default=32);args=p.parse_args()
torch.set_num_threads(1);torch.backends.cuda.matmul.allow_tf32=False
def sync():torch.cuda.synchronize()
if args.pause_pid:os.kill(args.pause_pid,signal.SIGSTOP)
try:
 saved=torch.load(ROOT/'learning-runs/centered-map-smoke/runs/rest-seed0/latest.pt',map_location='cpu',weights_only=False)
 obs=saved['env_obs'][:args.batch].cuda();mask=saved['env_mask'][:args.batch].cuda()
 model=Policy().cuda().eval();model.load_state_dict(saved['model'])
 with torch.no_grad():ref,rv=model(obs,mask);ref=ref.probs.float();rv=rv.float()
 results=[]
 for fused,layout,amp in [(False,'contiguous',False),(True,'channels_last',False),(True,'channels_last',True)]:
  model.fast_maps=fused
  model.to(memory_format=torch.channels_last if layout=='channels_last' else torch.contiguous_format)
  def context():return torch.autocast('cuda',dtype=torch.float16,enabled=amp)
  def forward():
   with context():return model(obs,mask)
  def backward():
   model.zero_grad(set_to_none=True)
   with context():
    dist,value=model(obs,mask);loss=value.float().square().mean()-dist.entropy().float().mean()
   loss.backward()
  for _ in range(3):
   with torch.no_grad():forward()
   backward()
  sync();start=time.perf_counter()
  with torch.no_grad():
   for _ in range(10):forward()
  sync();inference=(time.perf_counter()-start)/10
  start=time.perf_counter()
  for _ in range(10):backward()
  sync();training=(time.perf_counter()-start)/10
  with torch.no_grad():dist,value=forward()
  row=dict(fused=fused,layout=layout,amp=amp,batch=args.batch,inference_ms=inference*1000,forward_backward_ms=training*1000,max_probability_error=float((dist.probs.float()-ref).abs().max()),max_value_error=float((value.float()-rv).abs().max()),greedy_agreement=float((dist.probs.argmax(1)==ref.argmax(1)).float().mean()),finite_gradients=all(p.grad is not None and p.grad.isfinite().all().item() for p in model.parameters()))
  results.append(row);print(row,flush=True)
  if not amp and layout=='contiguous':
   with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU,torch.profiler.ProfilerActivity.CUDA],record_shapes=True) as prof:
    backward();sync()
   table=prof.key_averages().table(sort_by='self_cuda_time_total',row_limit=15)
   print(table,flush=True);(ROOT/'results/centered-map-profile.txt').write_text('\n'.join(line.rstrip() for line in table.splitlines())+'\n')
 (ROOT/'results/centered-map-performance.json').write_text(json.dumps(results,indent=2)+'\n')
finally:
 if args.pause_pid:os.kill(args.pause_pid,signal.SIGCONT)
