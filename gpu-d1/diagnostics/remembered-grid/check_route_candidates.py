"""Hand-constructed routing contracts, independent of simulator truth tables."""
import torch
from route_comparison import Router,Agent,Spatial,S
from run import save_json
from runtime import ROOT

def main():
    torch.set_num_threads(1);router=Router()
    g=torch.zeros(3,11,70,80,device='cuda',dtype=torch.uint8);g[:,1]=255
    # Straight passage, forced U detour, and disconnected remembered floor.
    paths=[[(x,10) for x in range(10,16)],
           [(10,y) for y in range(10,15)]+[(x,14) for x in range(11,17)]+[(16,y) for y in range(10,14)],
           [(10,10),(11,10),(15,10)]]
    for b,path in enumerate(paths):
        for x,y in path:g[b,0,y,x]=255;g[b,1,y,x]=0
        g[b,5,10,10]=255
    g[0,4,10,15]=255;g[1,4,10,16]=255;g[2,4,10,15]=255
    m=torch.zeros(3,19,device='cuda');m[:,16]=1;m[0,1]=1;m[1,2]=1;m[2,1]=1
    first,candidates,goal,action=router(g,m)
    assert action.tolist()==[1,2,16]
    assert goal.tolist()==[815,816,-1]
    assert first[1,816]==2 and not candidates[2,815]
    # No hidden-floor inference: replacing a known wall with unknown terrain
    # may create a frontier but must not make the remote stair reachable.
    g[2,1,10,12:15]=0
    first,candidates,goal,action=router(g,m);assert first[2,815]==-1 and not candidates[2,815]
    # Candidate masks and continuation execute one adjacent move, never teleport.
    agent=Agent(planner=True,oracle=True);s=torch.tensor([[1.,.2,10.,10.]]*3,device='cuda')
    a,data=agent.decide(g,m,s);assert a[:2].tolist()==[1,2]
    assert (data[1].gather(1,data[2][:,None])>0).all()
    _,dm,labels,_,_=agent.prepare(g,m,s);assert dm[:2,S].all() and (labels[:2]==S).all()
    agent.reset_cache();assert agent.goal is None
    # A true full-resolution map distinction survives model inputs.
    model=Spatial(20).cuda();x=data[0];a,d=model(x);loss=a.square().mean()+d.square().mean();loss.backward()
    assert model.gates.weight.grad.abs().sum()>0
    save_json(ROOT/'results/route-comparison-check.json',dict(passed=True,straight=True,detour=True,unknown_not_traversed=True,unreachable_stairs_excluded=True,continuation=True,spatial_recurrence_gradient=True))
    print('routing checks passed',flush=True)

if __name__=='__main__':main()
