"""One-pass / spatial recurrence / learned destinations with analytical BFS.

Fresh policies; same exact observed maps, layout splits, physical turn deadline,
teacher information and update count. Different action/target spaces are explicit.
"""
import argparse,ctypes as C,hashlib,json,subprocess,time
from pathlib import Path
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F
from run import evaluate,save_json
from runtime import ROOT,OUT
from fullsize_navigation import FullEnv,build_full
from native_curriculum import factory

S=5600
class Router:
    def __init__(self):
        src=Path(__file__).with_name('route_candidates.cpp');lib=OUT/'route-candidates.so';stamp=OUT/'route-candidates.sha256'
        digest=hashlib.sha256(src.read_bytes()).hexdigest()
        if not lib.exists() or not stamp.exists() or stamp.read_text()!=digest:
            subprocess.run(['g++','-O3','-std=c++17','-shared','-fPIC',str(src),'-o',str(lib)],check=True);stamp.write_text(digest)
        self.lib=C.CDLL(str(lib));self.lib.routes.argtypes=[C.c_int]+[C.c_void_p]*6
    def __call__(self,g,mask):
        g=np.ascontiguousarray(g.cpu().numpy(),dtype=np.uint8);m=np.ascontiguousarray(mask.cpu().numpy(),dtype=np.float32);n=len(g)
        first=np.empty((n,S),np.int8);cand=np.empty((n,S),np.uint8);goal=np.empty(n,np.int64);action=np.empty(n,np.int64)
        self.lib.routes(n,*[x.ctypes.data for x in (g,m,first,cand,goal,action)])
        return [torch.from_numpy(x).cuda() for x in (first,cand,goal,action)]

class Spatial(nn.Module):
    def __init__(self,iterations):
        super().__init__();self.iterations=iterations
        self.input=nn.Sequential(nn.PixelUnshuffle(4),nn.Conv2d(8*16,16,3,padding=1),nn.ReLU())
        self.gates=nn.Conv2d(32,32,3,padding=1);self.candidate=nn.Conv2d(32,16,3,padding=1)
        self.decode=nn.Sequential(nn.Conv2d(24,16,3,padding=1),nn.ReLU())
        self.moves=nn.Conv2d(16,19,1);self.dest=nn.Conv2d(16,1,1);self.special=nn.Linear(16,3)
    def forward(self,x):
        inputs=self.input(F.pad(x,(0,0,0,2)));h=torch.zeros_like(inputs)
        for _ in range(self.iterations):
            reset,update=self.gates(torch.cat([inputs,h],1)).sigmoid().chunk(2,1)
            new=self.candidate(torch.cat([inputs,reset*h],1)).tanh();h=(1-update)*h+update*new
        z=self.decode(torch.cat([x,F.interpolate(h,size=(70,80),mode='nearest')],1))
        pos=x[:,5].flatten(1).argmax(1);local=z.flatten(2).gather(2,pos[:,None,None].expand(-1,16,1)).squeeze(2)
        direct=self.moves(z).flatten(2).gather(2,pos[:,None,None].expand(-1,19,1)).squeeze(2)
        destinations=torch.cat([self.dest(z).flatten(1),self.special(local)],1)
        return direct,destinations

class Agent:
    def __init__(self,model=None,planner=False,oracle=False,random_dest=False):
        self.model=model;self.planner=planner;self.oracle=oracle;self.random_dest=random_dest;self.router=Router();self.reset_cache();self.switches=0;self.continues=0
    def reset_cache(self):self.goal=None
    def prepare(self,g,m,s):
        n=len(g)
        if self.goal is None:self.goal=torch.full((n,),-1,device='cuda',dtype=torch.long)
        floor=g[:,0]>0;wall=g[:,1]>0;visited=(g[:,2]>0)&floor
        x=torch.stack([~(floor|wall),wall,floor&~visited,visited,g[:,4]>0,g[:,5]>0],1).float()
        last=torch.zeros(n,S,device='cuda');last.scatter_(1,self.goal.clamp_min(0)[:,None],(self.goal>=0).float()[:,None])
        x=torch.cat([x,last.reshape(n,1,70,80),s[:,1,None,None,None].expand(-1,1,70,80)],1)
        first,cand,target,act=self.router(g,m)
        cont=(self.goal>=0)&(first.gather(1,self.goal.clamp_min(0)[:,None]).squeeze(1)>=0)
        dm=torch.cat([cand.bool(),cont[:,None],(m[:,16]>0)[:,None],(m[:,18]>0)[:,None]],1)
        label=torch.where(target>=0,target,S+1)
        label=torch.where(cont&(self.goal==target),S,label);label=torch.where(m[:,18]>0,S+2,label)
        return x,dm,label,act,first
    @torch.no_grad()
    def decide(self,g,m,s,teacher=False):
        x,dm,label,act,first=self.prepare(g,m,s)
        if self.random_dest:
            weights=dm[:,:S].float();none=weights.sum(1)==0;weights[none,0]=1
            choice=torch.multinomial(weights,1).squeeze(1);choice=torch.where(none,S+1,choice)
            choice=torch.where(dm[:,S],S,choice);choice=torch.where(dm[:,S+2],S+2,choice)
        elif teacher or self.oracle:choice=label if self.planner else act
        else:
            with torch.autocast('cuda',dtype=torch.float16):a,d=self.model(x)
            choice=(d.float().masked_fill(~dm,-1e9) if self.planner else a.float().masked_fill(m==0,-1e9)).argmax(1)
        if self.planner:
            dest=choice<S;self.switches+=int((dest&(choice!=self.goal)).sum());self.continues+=int((choice==S).sum())
            self.goal=torch.where(dest,choice,self.goal)
            action=first.gather(1,self.goal.clamp_min(0)[:,None]).squeeze(1).long()
            action=torch.where(choice==S+1,16,action);action=torch.where(choice==S+2,18,action)
            assert (action>=0).all()
        else:action=choice
        assert (m.gather(1,action[:,None]).squeeze(1)>0).all()
        return action,(x,dm if self.planner else m.bool(),label if self.planner else act)
    def __call__(self,g,m,s,intervene=None):
        assert intervene is None
        a,_=self.decide(g,m,s);return torch.zeros_like(m).scatter_(1,a[:,None],1.)

class Buffer:
    def __init__(self,planner,capacity=4096):
        self.x=torch.empty(capacity,8,70,80,device='cuda',dtype=torch.uint8)
        self.time=torch.empty(capacity,device='cuda');self.m=torch.empty(capacity,S+3 if planner else 19,device='cuda',dtype=torch.bool)
        self.y=torch.empty(capacity,device='cuda',dtype=torch.long);self.n=0;self.cursor=0;self.capacity=capacity
    def add(self,data,active):
        x,m,y=data;ids=active.nonzero().flatten();n=len(ids);ix=(torch.arange(n,device='cuda')+self.cursor)%self.capacity
        self.x[ix]=x[ids].to(torch.uint8);self.time[ix]=x[ids,7,0,0];self.m[ix]=m[ids];self.y[ix]=y[ids]
        self.cursor=(self.cursor+n)%self.capacity;self.n=min(self.capacity,self.n+n)
    def loss(self,model,planner):
        ix=torch.randint(self.n,(32,),device='cuda');x=self.x[ix].float();x[:,7]=self.time[ix,None,None]
        with torch.autocast('cuda',dtype=torch.float16):a,d=model(x)
        logits=(d if planner else a).float().masked_fill(~self.m[ix],-1e9)
        return F.cross_entropy(logits,self.y[ix])

def collect(env,agent,buffer,teacher,seed,steps=256):
    torch.manual_seed(seed);env.reset(seed=seed,labels=False);agent.reset_cache();count=0
    for _ in range(steps):
        action,data=agent.decide(env.grid,env.mask,env.stats,teacher);buffer.add(data,env.active);count+=int(env.active.sum())
        env.step(action,limit=1024,labels=False)
        if not env.active.any():break
    return count

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--arm',choices=['oracle','random','onepass','recurrent','planner'],required=True);ap.add_argument('--updates',type=int,default=2000);ap.add_argument('--smoke',action='store_true');args=ap.parse_args()
    torch.set_num_threads(1);torch.manual_seed(0);torch.backends.cudnn.benchmark=True;build_full()
    name='route-comparison-'+args.arm+('-smoke' if args.smoke else '');folder=OUT/name;folder.mkdir(exist_ok=True)
    path=ROOT/'results'/f'{name}.json'
    if (folder/'latest.pt').exists():raise RuntimeError('Refusing to overwrite')
    report=dict(arm=args.arm,seed=0,deadline=1024,updates=args.updates,history=[],scope='From scratch; enemy-free native80x70; exact remembered terrain only. One physical step/decision. Planner alone receives frontier-region/stair candidate mask and persistent selected-goal marker. Analytical routing and different supervision are part of treatment. 1 vs 20 spatial updates; same parameter shapes. Not PPO.',source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    if args.arm in ('oracle','random'):
        agent=Agent(planner=True,oracle=args.arm=='oracle',random_dest=args.arm=='random')
        for split in ['validation','test']:
            for band,cls in [('middle',factory(1)),('longer',FullEnv)]:
                key=band+'_'+split;report[key]=evaluate(agent,split,limit=1024,env_class=cls);print(key,report[key]['summary'],flush=True)
        report['finished']=True;save_json(path,report);return
    planner=args.arm=='planner';model=Spatial(1 if args.arm=='onepass' else 20).cuda();agent=Agent(model,planner)
    report['configuration']=dict(train_layouts=64,validation_layouts=16,test_layouts=32,collection_cap=256,environment_batch=32,replay_capacity_per_buffer=4096,training_batch_per_buffer=32,expert_loss_fraction=.5,learning_rate=3e-4,spatial_iterations=model.iterations,parameters=sum(p.numel() for p in model.parameters()),warm_start=False)
    env=factory(1)('train',32);expert=Buffer(planner);learner=Buffer(planner)
    opt=torch.optim.Adam(model.parameters(),lr=3e-4);scaler=torch.amp.GradScaler('cuda',init_scale=1024)
    start=time.monotonic();excluded=0.;decisions=collect(env,agent,expert,True,11000,32 if args.smoke else 256)
    decisions+=collect(env,agent,learner,False,11050,32 if args.smoke else 256);best=-1
    for step in range(1,(2 if args.smoke else args.updates)+1):
        opt.zero_grad(set_to_none=True);loss=.5*(expert.loss(model,planner)+learner.loss(model,planner));assert torch.isfinite(loss)
        scaler.scale(loss).backward();scaler.unscale_(opt);nn.utils.clip_grad_norm_(model.parameters(),1);scaler.step(opt);scaler.update()
        if step%100==0:decisions+=collect(env,agent,learner,False,11000+step)
        if step%500==0:decisions+=collect(env,agent,expert,True,16000+step)
        if step%500==0 or step==args.updates or args.smoke:
            trained=time.monotonic()-start-excluded;t=time.monotonic();val={} if args.smoke else evaluate(agent,'validation',limit=1024,env_class=factory(1));excluded+=time.monotonic()-t
            score=0 if args.smoke else sum(v['exit'] for v in val['summary'].values())/2
            row=dict(step=step,training_seconds=trained,decisions=decisions,loss=float(loss.detach()),validation=val.get('summary',{}));report['history'].append(row)
            payload=dict(model=model.state_dict(),step=step,arm=args.arm);torch.save(payload,folder/'latest.pt')
            if score>best:best=score;report['selected']=row;torch.save(payload,folder/'selected.pt')
            save_json(path,report);print(json.dumps(row),flush=True)
    model.load_state_dict(torch.load(folder/'selected.pt',weights_only=False)['model'])
    if not args.smoke:
        for name,cls in [('middle_test',factory(1)),('longer_test',FullEnv)]:report[name]=evaluate(agent,'test',limit=1024,env_class=cls);save_json(path,report)
    report['finished']=True;save_json(path,report)

if __name__=='__main__':main()
