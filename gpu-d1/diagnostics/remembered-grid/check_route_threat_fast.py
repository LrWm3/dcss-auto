import ctypes as C,json,time
import torch
from route_threat_ppo import PPO,collect,update,Agent,ThreatEnv,FOLDER_OUT,ROOT,build,save_json
from route_threat_fast import GraphInference,GPURouter
from benchmark_route_threat import timing

def main():
    torch.set_num_threads(1);torch.manual_seed(0);torch.backends.cudnn.benchmark=True;build()
    e=ThreatEnv('train',32);e.reset(40000);agent=Agent(memory=True)
    e.lib.threat_export_reference.argtypes=e.lib.threat_export.argtypes
    refs=[torch.empty_like(t) for t in [e.grid,e.mask,e.stats,e.meta]]
    for step in range(30):
        e.check(e.lib.threat_export_reference(e.state.data_ptr(),e.memory.data_ptr(),e.batch,C.byref(e.tables),*[v.data_ptr() for v in refs],e.stream))
        for actual,ref in zip([e.grid,e.mask,e.stats,e.meta],refs):assert torch.equal(actual,ref),step
        action,_=agent.decide(e,expert=True);e.step(action)
    gpu=GPURouter();router_checks=0
    for _ in range(30):
        actual=gpu(e.grid[:,:11],e.mask);expected=agent.router(e.grid[:,:11],e.mask)
        for a,b in zip(actual,expected):assert torch.equal(a,b)
        router_checks+=e.batch;action,_=agent.decide(e,expert=True);e.step(action)
    router_ms=timing(lambda:gpu(e.grid[:,:11],e.mask))
    model=PPO(FOLDER_OUT/'route-threat-visible/selected.pt');model.actor.to(memory_format=torch.contiguous_format);e.reset(40000);agent.reset_cache();x,m,_,_=agent.prepare(e,labels=False);x=x.half()
    with torch.no_grad():
        ref=model.raw(x,m);graph=GraphInference(model);actual=graph.forward(x,m)
        for a,b in zip(actual,ref):torch.testing.assert_close(a,b,atol=.001,rtol=.001)
        saved=actual[0].clone();model.actor.special.bias[17].add_(1.)
        updated=graph.forward(x,m)
        for a,b in zip(updated,model.raw(x,m)):torch.testing.assert_close(a,b,atol=.001,rtol=.001)
        assert not torch.equal(saved,updated[0]);assert torch.equal(saved,actual[0]),'graph results alias output storage'
        eager_ms=timing(lambda:model(x,m));graph_ms=timing(lambda:graph(x,m))
        nchw=model.raw(x,m);model.to(memory_format=torch.channels_last);last=model.raw(x,m)
        valid=m;maxerr=float((last[0][valid]-nchw[0][valid]).abs().max());assert maxerr<.02,maxerr
        graph_last=GraphInference(model);last_ms=timing(lambda:graph_last(x,m))
    result=dict(gpu_router_ms=router_ms,gpu_router_exact_cases=router_checks,export_bitwise_equal_states=30,graph_parameter_updates_visible=True,graph_outputs_do_not_alias=True,eager_ms=eager_ms,graph_ms=graph_ms,channels_last_graph_ms=last_ms,channels_last_max_logit_difference=maxerr,fast_export_ms=timing(e.observe),reference_export_ms=timing(lambda:e.lib.threat_export_reference(e.state.data_ptr(),e.memory.data_ptr(),e.batch,C.byref(e.tables),*[v.data_ptr() for v in refs],e.stream)))
    model.inference=graph_last;agent=Agent(model.actor,False);agent.router=gpu;opt=torch.optim.Adam(model.parameters(),lr=1e-5);scaler=torch.amp.GradScaler('cuda',init_scale=1024)
    t=time.monotonic();data,metrics=collect(e,agent,model);torch.cuda.synchronize();result['collection_seconds']=time.monotonic()-t
    result['update']=update(model,opt,scaler,data);torch.cuda.synchronize();result['full_rollout_and_update_seconds']=time.monotonic()-t;result['decisions_per_second']=2048/result['full_rollout_and_update_seconds']
    save_json(ROOT/'results/route-threat-performance.json',result);print(json.dumps(result),flush=True)

if __name__=='__main__':main()
