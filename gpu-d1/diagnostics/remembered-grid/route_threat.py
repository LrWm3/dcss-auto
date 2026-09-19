"""Matched destination-routing screen with/without remembered enemy observations.

Both arms imitate the same observation-limited teacher. No pressure layouts are
used for training or checkpoint selection. This is DAgger, not PPO.
"""
import argparse,ctypes as C,hashlib,json,subprocess,time
from pathlib import Path
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F
from run import save_json
from route_comparison import Spatial,Router,S
from route_threat_env import ThreatEnv,build,pressure_maps,FOLDER_OUT,HERE,ROOT,OUT

CHANNELS=19
ACTIONS=S+20 # destinations, continue, then the 19 individual actions
SOURCE=OUT/'route-comparison-planner/selected.pt'

class ThreatPolicy(Spatial):
    def __init__(self):
        super().__init__(20)
        self.input[1]=nn.Conv2d(CHANNELS*16,16,3,padding=1)
        self.decode[0]=nn.Conv2d(CHANNELS+16,16,3,padding=1)
        self.special=nn.Linear(16,20)
        prior=Spatial(20);prior.load_state_dict(torch.load(SOURCE,weights_only=False)['model'])
        with torch.no_grad():
            own=self.state_dict();old=prior.state_dict()
            for k,v in own.items():
                if v.shape==old[k].shape:v.copy_(old[k])
            self.input[1].weight.zero_();self.input[1].weight[:,:128].copy_(prior.input[1].weight)
            self.decode[0].weight.zero_();self.decode[0].weight[:,:8].copy_(prior.decode[0].weight[:,:8]);self.decode[0].weight[:,CHANNELS:].copy_(prior.decode[0].weight[:,8:])
            # Transfer movement logits into primitive actions; destination and
            # CONTINUE / WAIT / EXIT logits preserve the successful navigator.
            self.special.weight[1:].copy_(prior.moves.weight[:,:,0,0]);self.special.bias[1:].copy_(prior.moves.bias)
            for new,old_index in [(0,0),(17,1),(19,2)]:
                self.special.weight[new].copy_(prior.special.weight[old_index]);self.special.bias[new].copy_(prior.special.bias[old_index])
    def forward(self,x,return_features=False):
        inputs=self.input(F.pad(x,(0,0,0,2)));h=torch.zeros_like(inputs)
        # Opt-in benchmark: retain checkpoint keys and differentiate through
        # the cached input projections; never cache across policy forwards.
        hoist=getattr(self,'hoist_inputs',False)
        if hoist:
            gi=F.conv2d(inputs,self.gates.weight[:,:16],self.gates.bias,padding=1)
            ci=F.conv2d(inputs,self.candidate.weight[:,:16],self.candidate.bias,padding=1)
        for _ in range(self.iterations):
            if hoist:
                reset,update=(gi+F.conv2d(h,self.gates.weight[:,16:],padding=1)).sigmoid().chunk(2,1)
                new=(ci+F.conv2d(reset*h,self.candidate.weight[:,16:],padding=1)).tanh()
            else:
                reset,update=self.gates(torch.cat([inputs,h],1)).sigmoid().chunk(2,1)
                new=self.candidate(torch.cat([inputs,reset*h],1)).tanh()
            h=(1-update)*h+update*new
        z=self.decode(torch.cat([x,F.interpolate(h,size=(70,80),mode='nearest')],1))
        pos=x[:,5].flatten(1).argmax(1);local=z.flatten(2).gather(2,pos[:,None,None].expand(-1,16,1)).squeeze(2)
        logits=torch.cat([self.dest(z).flatten(1),self.special(local)],1)
        return (logits,local) if return_features else logits

class Teacher:
    def __init__(self):
        src=HERE/'route_threat_teacher.cpp';lib=FOLDER_OUT/'teacher.so';stamp=FOLDER_OUT/'teacher.sha256'
        digest=hashlib.sha256(src.read_bytes()).hexdigest()
        if not lib.exists() or not stamp.exists() or stamp.read_text()!=digest:
            subprocess.run(['g++','-O3','-std=c++17','-shared','-fPIC',str(src),'-o',str(lib)],check=True);stamp.write_text(digest)
        self.lib=C.CDLL(str(lib));self.lib.threat_labels.argtypes=[C.c_int]+[C.c_void_p]*7
        d=json.loads((HERE.parent/'d1-anonymous-power/distribution.json').read_text());self.templates=d['train_templates']
        self.risks=torch.tensor([t['risk_by_player'] for t in self.templates],device='cuda')
    def __call__(self,g,m,s,first,cand):
        pi=(s[:,4,None]-s.new_tensor([10,18,30])).abs().argmin(1)*3+(s[:,5,None]-s.new_tensor([2,4,6])).abs().argmin(1)
        risk=torch.zeros_like(g[:,0],dtype=torch.float32)
        for j,t in enumerate(self.templates):
            match=(g[:,7]==t['hp'])&(g[:,8]==t['damage_cap'])&(g[:,11]>0)
            # Conservative heuristic at less than full HP, not recalibrated odds.
            r=(self.risks[j,pi]+(1-s[:,0]).clamp(0,1)*.5).clamp(0,1)
            risk=torch.where(match,r[:,None,None],risk)
        arrays=[np.ascontiguousarray(v.cpu().numpy()) for v in (g,m,s,first,cand,risk)]
        labels=np.empty(len(g),np.int64);self.lib.threat_labels(len(g),*[v.ctypes.data for v in arrays],labels.ctypes.data)
        return torch.from_numpy(labels).cuda()

class Agent:
    def __init__(self,model=None,memory=True,teacher=None):
        self.model=model;self.memory=memory;self.router=Router();self.teacher=teacher or Teacher();self.reset_cache()
    def reset_cache(self):self.goal=None
    def prepare(self,e,labels=True):
        g=e.grid;m=e.mask;s=e.stats;n=len(g)
        if self.goal is None:self.goal=torch.full((n,),-1,device='cuda',dtype=torch.long)
        first,cand,_,_=self.router(g[:,:11],m)
        floor=g[:,0]>0;wall=g[:,1]>0;visited=(g[:,2]>0)&floor
        base=torch.stack([~(floor|wall),wall,floor&~visited,visited,g[:,4]>0,g[:,5]>0],1).float()
        last=torch.zeros(n,S,device='cuda');last.scatter_(1,self.goal.clamp_min(0)[:,None],(self.goal>=0).float()[:,None])
        x=torch.cat([base,last.reshape(n,1,70,80),s[:,1,None,None,None].expand(-1,1,70,80)],1)
        enemies=g[:,6:].float()/255.
        if not self.memory:enemies=enemies*(g[:,12:13]>0)
        # Raw HP/damage scales are stable across player strengths, alongside HP fraction.
        player=torch.stack([s[:,0],s[:,4]/30,s[:,5]/6],1)[:,:,None,None].expand(-1,-1,70,80)
        x=torch.cat([x,enemies,player],1)
        awake=((g[:,12]>0)&(g[:,9]>0)).flatten(1).any(1)
        cont=(self.goal>=0)&(first.gather(1,self.goal.clamp_min(0)[:,None]).squeeze(1)>=0)&~awake
        mask=torch.cat([cand.bool()&~awake[:,None],cont[:,None],m.bool()],1)
        label=None
        if labels:
            label=self.teacher(g,m,s,first,cand)
            label=torch.where((label==self.goal)&cont,S,label)
            assert mask.gather(1,label[:,None]).all(), 'illegal teacher label'
        return x,mask,label,first
    @torch.no_grad()
    def decide(self,e,expert=False,erase_memory=False,sample=False):
        x,mask,label,first=self.prepare(e)
        if erase_memory:x[:,8:16]*=(e.grid[:,12:13]>0)
        if expert:choice=label
        else:
            with torch.autocast('cuda',dtype=torch.float16):logits=self.model(x)
            logits=logits.float().masked_fill(~mask,-1e9)
            choice=torch.distributions.Categorical(logits=logits,validate_args=False).sample() if sample else logits.argmax(1)
        dest=choice<S;self.goal=torch.where(dest,choice,self.goal)
        step=first.gather(1,self.goal.clamp_min(0)[:,None]).squeeze(1).long()
        action=torch.where(choice<=S,step,choice-(S+1))
        assert (action>=0).all() and e.mask.gather(1,action[:,None]).all()
        return action,(x,mask,label)

class Buffer:
    def __init__(self,capacity=2048):
        self.x=torch.empty(capacity,CHANNELS,70,80,device='cuda',dtype=torch.float16)
        self.mask=torch.empty(capacity,ACTIONS,device='cuda',dtype=torch.bool);self.y=torch.empty(capacity,device='cuda',dtype=torch.long)
        self.n=0;self.cursor=0;self.capacity=capacity
    def add(self,data,active):
        x,m,y=data;ids=active.nonzero().flatten();ix=(torch.arange(len(ids),device='cuda')+self.cursor)%self.capacity
        self.x[ix]=x[ids].half();self.mask[ix]=m[ids];self.y[ix]=y[ids];self.cursor=(self.cursor+len(ids))%self.capacity;self.n=min(self.capacity,self.n+len(ids))
    def loss(self,model):
        ix=torch.randint(self.n,(32,),device='cuda')
        with torch.autocast('cuda',dtype=torch.float16):z=model(self.x[ix])
        return F.cross_entropy(z.float().masked_fill(~self.mask[ix],-1e9),self.y[ix])

def collect(e,agent,buffer,expert,seed,steps=256):
    torch.manual_seed(seed);e.reset(seed);agent.reset_cache();decisions=0
    for _ in range(steps):
        action,data=agent.decide(e,expert);buffer.add(data,e.active);decisions+=int(e.active.sum());e.step(action)
        if not e.active.any():break
    return decisions

@torch.no_grad()
def episode(e,agent,expert=False,erase=False,limit=2048):
    agent.reset_cache();n=e.batch;initial=e.meta[:,5].clone();terminal=torch.zeros(n,6,device='cuda');prev=e.meta[:,0].clone();pp=prev.clone();reversals=torch.zeros(n,device='cuda');stale=torch.zeros(n,device='cuda');waits=torch.zeros(n,device='cuda')
    for _ in range(limit):
        active=e.active.clone();p=e.meta[:,0].clone();a,_=agent.decide(e,expert,erase)
        waits+=active&(a==16);stale+=active&(e.grid[:,13].flatten(1).sum(1)>0)
        e.step(a,limit);reversals+=active&(e.meta[:,0]==pp)&(p!=pp);pp=p
        end=active&~e.active;terminal[end]=e.out[end][:,[2,6,7,5,3,4]]
        if not e.active.any():break
    assert not e.active.any()
    return [dict(exit=int(z[0]),death=int(z[1]),timeout=int(z[2]),turns=float(z[3]-initial[j]),kills=float(z[4]),reversals=int(reversals[j]),waits=int(waits[j]),stale_decisions=int(stale[j])) for j,z in enumerate(terminal)]

def summarize(rows):return {k:float(np.mean([r[k] for r in rows])) for k in rows[0] if k not in ('scenario','map','known','length','symmetry','condition')}

def evaluate(agent,split='validation',expert=False,pressure=False,erase=False,small=False):
    start=time.monotonic();rows=[]
    if not pressure:
        e=ThreatEnv(split,32)
        for seed in ([70000] if small else [70000,71000,72000,73000]):
            e.reset(seed);rs=episode(e,agent,expert,erase)
            rows+=rs
    else:
        e=ThreatEnv('test',64,map_dir=pressure_maps())
        for condition,hp,damage in [('weak',6,4),('strong',24,20)]:
            ids=torch.arange(64,device='cuda');power=torch.tensor([18,4,hp,damage],device='cuda').expand(64,-1)
            e.reset(81000,ids,power);rs=episode(e,agent,expert,erase)
            for j,r in enumerate(rs):r.update(scenario=j,known=j%2,length=[4,8,16,24][j//16],symmetry=(j//2)%8,condition=condition)
            rows+=rs
    groups={'all':summarize(rows)}
    if pressure:
        for condition in ['weak','strong']:
            for known in [0,1]:groups[f'{condition}_{"known" if known else "unknown"}']=summarize([r for r in rows if r['condition']==condition and r['known']==known])
    return dict(groups=groups,rows=rows,seconds=time.monotonic()-start)

def main():
    p=argparse.ArgumentParser();p.add_argument('--arm',choices=['memory','visible','teacher'],required=True);p.add_argument('--updates',type=int,default=2000);p.add_argument('--smoke',action='store_true');args=p.parse_args()
    torch.set_num_threads(1);torch.manual_seed(0);torch.backends.cudnn.benchmark=True;build()
    name='route-threat-'+args.arm+('-smoke' if args.smoke else '');folder=FOLDER_OUT/name;folder.mkdir(exist_ok=True)
    path=ROOT/'results'/f'{name}.json'
    if (folder/'latest.pt').exists() or path.exists():raise RuntimeError('Refusing to overwrite '+name)
    report=dict(arm=args.arm,seed=0,updates=args.updates,history=[],scope='DAgger; warm-start navigation; 24 calibrated anonymous enemies, 2048 physical turns, 64/16/32 native layout split; tactical individual actions; known-terrain BFS only. Same memory-informed teacher labels both arms; no pressure training.',source_checkpoint_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),source_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),HERE/'route_threat_env.py',HERE/'route_threat_native.cu',HERE/'route_threat_teacher.cpp']})
    if args.arm=='teacher':
        agent=Agent()
        for name,kwargs in [('ordinary',dict(split='test')),('pressure',dict(pressure=True))]:
            report[name]=evaluate(agent,expert=True,small=args.smoke,**kwargs);save_json(path,report);print(name,report[name]['groups'],flush=True)
        report['finished']=True;save_json(path,report);return
    model=ThreatPolicy().cuda();agent=Agent(model,args.arm=='memory');e=ThreatEnv('train',32)
    if not args.smoke:
        report['initial_validation']=evaluate(agent,small=True)
        print('initial_validation',report['initial_validation']['groups'],flush=True);save_json(path,report)
    expert=Buffer();learner=Buffer();opt=torch.optim.Adam(model.parameters(),lr=1e-4);scaler=torch.amp.GradScaler('cuda',init_scale=1024)
    start=time.monotonic();excluded=0.;steps=16 if args.smoke else 256
    decisions=collect(e,agent,expert,True,10000,steps)+collect(e,agent,learner,False,10100,steps);best=-1
    for update in range(1,(2 if args.smoke else args.updates)+1):
        opt.zero_grad(set_to_none=True);loss=.5*(expert.loss(model)+learner.loss(model));assert torch.isfinite(loss)
        scaler.scale(loss).backward();scaler.unscale_(opt);nn.utils.clip_grad_norm_(model.parameters(),1);scaler.step(opt);scaler.update()
        if update%100==0:decisions+=collect(e,agent,learner,False,20000+update)
        if update%500==0:decisions+=collect(e,agent,expert,True,30000+update)
        if update%500==0 or update==args.updates or args.smoke:
            seconds=time.monotonic()-start-excluded;t=time.monotonic();val={} if args.smoke else evaluate(agent,small=True);excluded+=time.monotonic()-t
            score=0 if args.smoke else val['groups']['all']['exit'];row=dict(update=update,loss=float(loss.detach()),training_seconds=seconds,decisions=decisions,validation=val.get('groups',{}));report['history'].append(row)
            payload=dict(model=model.state_dict(),update=update,arm=args.arm,optimizer=opt.state_dict(),scaler=scaler.state_dict());torch.save(payload,folder/'latest.pt')
            if score>best:best=score;report['selected']=row;torch.save(payload,folder/'selected.pt')
            print(json.dumps(row),flush=True);save_json(path,report)
    model.load_state_dict(torch.load(folder/'selected.pt',weights_only=False)['model'])
    if not args.smoke:
        for name,kwargs in [('ordinary',dict(split='test')),('pressure',dict(pressure=True))]:
            report[name]=evaluate(agent,**kwargs);print(name,report[name]['groups'],flush=True);save_json(path,report)
        if args.arm=='memory':report['pressure_erased']=evaluate(agent,pressure=True,erase=True)
    report['finished']=True;save_json(path,report)

if __name__=='__main__':main()
