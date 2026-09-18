"""Real transition tests for last-seen enemy memory and hybrid action masks."""
import ctypes as C
import json
import torch
from route_threat import Agent,ThreatPolicy,Teacher,S,build,ThreatEnv,pressure_maps,ROOT,save_json

def main():
    torch.set_num_threads(1);torch.manual_seed(0);build()
    e=ThreatEnv('test',1,map_dir=pressure_maps());e.reset(123,torch.tensor([0],device='cuda'),torch.tensor([[18,4,24,20]],device='cuda'))
    agent=Agent();x,mask,label,first=agent.prepare(e)
    assert e.grid[:,12].sum()>0 and not ((e.grid[:,12]>0)&(e.grid[:,9]>0)).any()
    assert mask[:,:S].any(), 'sleepers must not disable navigation'
    action,_=agent.decide(e,True);assert action.item()==3, 'teacher must backtrack west in canonical case'
    old=e.grid[:,6:].clone();e.step(action)
    assert e.grid[:,13].sum()>0 and e.grid[:,12].sum()==0
    assert torch.equal(e.grid[:,6:10],old[:,:4])
    a=Agent(memory=True);b=Agent(memory=False)
    xm,mm,ym,_=a.prepare(e);xv,mv,yv,_=b.prepare(e)
    assert xm[:,8:16].sum()>0 and xv[:,8:16].sum()==0
    assert torch.equal(mm,mv) and torch.equal(ym,yv), 'ablation must retain identical legality and labels'
    out=torch.zeros(6,device='cuda',dtype=torch.int32);p=C.c_void_p
    e.lib.threat_checks.argtypes=[p,p,p,p,p]
    e.check(e.lib.threat_checks(e.state.data_ptr(),e.memory.data_ptr(),C.byref(e.tables),out.data_ptr(),e.stream));assert out.eq(1).all()
    # Enter wake range from the same initial state and inspect actual observation.
    e.reset(123,torch.tensor([0],device='cuda'),torch.tensor([[18,4,24,20]],device='cuda'));e.step(torch.tensor([1],device='cuda'))
    assert ((e.grid[:,12]>0)&(e.grid[:,9]>0)).any()
    agent.reset_cache();_,mask,_,_=agent.prepare(e);assert not mask[:,:S+1].any() and mask[:,S+1:S+9].any()
    # Memory is episode-local, and normalized HP must use the varied maximum.
    e.reset(123,torch.tensor([0],device='cuda'),torch.tensor([[30,6,6,4]],device='cuda'))
    assert e.stats[0,0]==1 and e.stats[0,4]==30 and e.stats[0,5]==6 and not e.grid[:,13].any()
    # First layer can learn the new information; no frozen/zero-gradient branch.
    model=ThreatPolicy().cuda();a=Agent(model);x,mask,label,_=a.prepare(e)
    loss=torch.nn.functional.cross_entropy(model(x).masked_fill(~mask,-1e9),label);loss.backward()
    assert model.input[1].weight.grad[:,128:].abs().sum()>0
    result=dict(passed=True,checks=['hidden movement/damage/wake/death leave memory unchanged','visible empty square invalidates stale record','reobservation refreshes stats and age','visible identity reassociation removes duplicate','multiple enemies retained','reset clears memory','real retreat produces stale observation','visible-only ablation removes stale channels only','sleep allows destinations','awake encounter disables destinations but permits retreat','variable player stat normalization','new input channels receive gradients'])
    save_json(ROOT/'results/route-threat-check.json',result);print(json.dumps(result),flush=True)

if __name__=='__main__':main()
