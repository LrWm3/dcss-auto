"""Isolated timings and profiler trace for routing PPO; no training mutation."""
import json,time
import torch
from route_threat_ppo import PPO,collect,update,Agent,ThreatEnv,FOLDER_OUT,ROOT,build,save_json

def timing(fn,n=30):
    for _ in range(3):fn()
    torch.cuda.synchronize();t=time.perf_counter()
    for _ in range(n):fn()
    torch.cuda.synchronize();return (time.perf_counter()-t)*1000/n

def main():
    torch.set_num_threads(1);torch.manual_seed(0);torch.backends.cudnn.benchmark=True;build()
    model=PPO(FOLDER_OUT/'route-threat-visible/selected.pt');model.actor.to(memory_format=torch.contiguous_format);e=ThreatEnv('train',32);e.reset(40000);a=Agent(model.actor,False)
    with torch.no_grad():
        x,m,_,_=a.prepare(e,labels=False);x=x.half()
        result=dict(router_ms=timing(lambda:a.router(e.grid[:,:11],e.mask)),prepare_ms=timing(lambda:a.prepare(e,labels=False)),actor_value_ms=timing(lambda:model(x,m)),observe_ms=timing(e.observe))
    with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU,torch.profiler.ProfilerActivity.CUDA]) as prof:
        data,metrics=collect(e,a,model,8)
    print(prof.key_averages().table(sort_by='self_cuda_time_total',row_limit=12),flush=True)
    result['rollout']=metrics;prof.export_chrome_trace(str(FOLDER_OUT/'ppo-profile.json'))
    save_json(ROOT/'results/route-threat-performance-baseline.json',result);print(json.dumps(result),flush=True)

if __name__=='__main__':main()
