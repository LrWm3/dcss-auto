"""Coverage audit and matched DAgger/exact-map screens on middle routes."""
import argparse,fcntl,hashlib,json,time
from pathlib import Path
import torch
from torch import nn
from torch.nn import functional as F
from native_curriculum import factory,collect
from run import evaluate,save_json
from runtime import ROOT,OUT
from fullsize_navigation import FullEnv,build_full
from symbolic_fast import FastSymbolicPolicy
from symbolic_policy import categories
from symbolic_execution import PolicyExecution,StaticInference

SOURCE=OUT/'native-curriculum-seed0/selected.pt'

class ExactPolicy(FastSymbolicPolicy):
    """Retain the old branch, adding trainable processing of exact known terrain."""
    def __init__(self):
        super().__init__(True,True,True)
        self.exact=nn.Sequential(nn.Conv2d(6,8,3,padding=1),nn.ReLU(),nn.Conv2d(8,16,3,stride=2,padding=1),nn.ReLU(),nn.Conv2d(16,16,3,stride=2,padding=1),nn.ReLU(),nn.Flatten(),nn.Linear(16*18*20,96))
        nn.init.zeros_(self.exact[-1].weight);nn.init.zeros_(self.exact[-1].bias)
        self.exact.to(memory_format=torch.channels_last)
        yy,xx=torch.meshgrid(torch.arange(70),torch.arange(80),indexing='ij')
        bins=((yy*16//70)*16+xx*16//80).flatten()
        self.register_buffer('exact_bins',bins,persistent=False)
        self.register_buffer('exact_counts',torch.bincount(bins,minlength=256).float(),persistent=False)
    def prepare(self,g,s):
        local,_,tactical,stats=super().prepare(g,s)
        exact=torch.cat([categories(g),(g[:,4:6]>0).float()],1)
        return local,self._layout(exact),tactical,stats
    def encode_prepared(self,inputs,intervene=None):
        local,exact,tactical,stats=inputs;exact=exact.float();n=len(exact)
        glob=exact.new_zeros(n,6,256)
        glob.scatter_add_(2,self.exact_bins[None,None].expand(n,6,-1),exact.flatten(2))
        glob=torch.cat([glob[:,:4]/self.exact_counts[None,None],glob[:,4:].clamp(0,1)],1).reshape(n,6,16,16)
        global_features=self.global_net(self._layout(glob))+self.exact(self._layout(exact))
        return torch.cat([self.local(self._layout(local)),global_features,self.tactical(self._layout(tactical)),stats],1)


def make_model(exact=False):
    model=(ExactPolicy() if exact else FastSymbolicPolicy(True,True,True)).cuda()
    missing,unexpected=model.load_state_dict(torch.load(SOURCE,weights_only=False)['model'],strict=not exact)
    assert not unexpected and all(k.startswith('exact.') for k in missing)
    return model


class Buffer:
    def __init__(self,exact=False,balanced=False,capacity=1024):
        self.capacity=capacity;self.n=0;self.cursor=0;self.balanced=balanced
        shapes=[(5,15,15),(6,70,80) if exact else (6,16,16),(6,15,15),(2,)]
        self.p=[torch.empty(capacity,32,*s,device='cuda',dtype=torch.uint8 if exact and j==1 else torch.float32) for j,s in enumerate(shapes)]
        self.mask=torch.empty(capacity,32,19,device='cuda');self.label=torch.empty(capacity,32,device='cuda',dtype=torch.long);self.valid=torch.empty(capacity,32,device='cuda',dtype=torch.bool)
        self.group=torch.empty(capacity,32,device='cuda',dtype=torch.long);self.collected=torch.zeros(3,device='cuda',dtype=torch.long)
        self.sampled=torch.zeros(3,device='cuda',dtype=torch.long)
    def add(self,history):
        values=[torch.stack(x,1) for x in zip(*history)];ids=values[-1][:,16:].any(1).nonzero().flatten();n=len(ids)
        if not n:return
        ix=(torch.arange(n,device='cuda')+self.cursor)%self.capacity
        local,glob=values[:2];known=glob[:,:,4].flatten(2).any(2);near=local[:,:,4].flatten(2).any(2)
        group=torch.where(known,torch.where(near,1,2),0)
        for dst,src in zip(self.p+[self.mask,self.label,self.valid],values):dst[ix]=src[ids].to(dst.dtype)
        self.group[ix]=group[ids]
        for k in range(3):self.collected[k]+=((group[:,16:]==k)&values[-1][:,16:]).sum()
        self.cursor=(self.cursor+n)%self.capacity;self.n=min(self.capacity,self.n+n)
    def coverage(self):
        v=self.valid[:self.n,16:];g=self.group[:self.n,16:]
        return dict(collected=self.collected.tolist(),retained=[int(((g==k)&v).sum()) for k in range(3)],sampled=self.sampled.tolist(),sequences=self.n)
    def loss(self,model,execution,batch=16):
        if self.balanced:
            available=[]
            for k in range(3):
                ids=((self.group[:self.n,16:]==k)&self.valid[:self.n,16:]).any(1).nonzero().flatten()
                if len(ids):available.append(ids)
            ix=torch.cat([a[torch.randint(len(a),((batch+j)//len(available),),device='cuda')] for j,a in enumerate(available)])
            assert len(ix)==batch
        else:ix=torch.randint(self.n,(batch,),device='cuda')
        v=self.valid[ix];assert ((v[:,:16].all(1))|(~v[:,:16].any(1))).all()
        with torch.no_grad(),torch.autocast('cuda',dtype=torch.float16):
            x=execution.encode([p[ix,:16].flatten(0,1).float() for p in self.p]).reshape(batch,16,-1)
            _,h=model.sequence(x);h=h*v[:,15,None]
        with torch.autocast('cuda',dtype=torch.float16):
            x=execution.encode([p[ix,16:].flatten(0,1).float() for p in self.p]).reshape(batch,16,-1)
            z,_=model.sequence(x,h);logits=model.policy(z).float().masked_fill(self.mask[ix,16:]==0,-1e9)
        target=self.label[ix,16:];valid=v[:,16:];groups=self.group[ix,16:]
        assert (self.mask[ix,16:].gather(-1,target[...,None]).squeeze(-1)[valid]>0).all()
        losses=F.cross_entropy(logits.flatten(0,1),target.flatten(),reduction='none').reshape(batch,16)
        for k in range(3):self.sampled[k]+=((groups==k)&valid).sum()
        if self.balanced:
            counts=torch.stack([((groups==k)&valid).sum() for k in range(3)])
            weighted=torch.stack([(losses*((groups==k)&valid)).sum()/counts[k].clamp_min(1) for k in range(3)])
            loss=weighted.sum()/(counts>0).sum()
        else:loss=(losses*valid).sum()/valid.sum()
        return loss,int(valid.sum())


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--arm',choices=['audit','control','balanced','exact'],required=True);ap.add_argument('--updates',type=int,default=2000);ap.add_argument('--smoke',action='store_true');ap.add_argument('--name');args=ap.parse_args()
    torch.set_num_threads(1);torch.manual_seed(0);torch.backends.cudnn.benchmark=True;build_full()
    name=args.name or 'native-remedy-'+args.arm+('-smoke' if args.smoke else '')
    folder=OUT/name;folder.mkdir(exist_ok=True);lock=(folder/'run.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if (folder/'latest.pt').exists():raise RuntimeError('Refusing to overwrite')
    model=make_model(args.arm=='exact');execution=PolicyExecution(model,compiled=True);policy=StaticInference(execution,amp=True,graphed=True)
    env=factory(1)('train',32)
    report=dict(arm=args.arm,configuration=dict(seed=0,updates=args.updates,smoke=args.smoke,lr=1e-4,amp_initial_scale=1024,burn_in=16,learn_steps=16,sequences_per_buffer_batch=16,buffer_capacity=1024,expert_loss_fraction=.5,learner_teacher_probability=.1 if args.arm=='control' else 0,deadline=1024,collection_cap=512),groups=['no_known_stairs','known_stairs_in_crop','known_stairs_outside_crop'],source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),parameters=sum(p.numel() for p in model.parameters()),history=[],scope='One-seed matched additional training on middle band. Exact arm adds capacity and raw observed map detail; this is not a parameter-matched isolation of information loss. No route/distance hints.')
    if args.arm=='audit':
        for label,beta in [('expert',1),('mixed',.1),('pure_learner',0)]:
            buffer=Buffer();torch.manual_seed(8811)
            for j in range(4):
                torch.manual_seed(8811+j);collect(env,buffer,model,policy,beta,11000+j)
            report[label]=buffer.coverage();print(label,report[label],flush=True);del buffer
        save_json(ROOT/'results'/f'{name}.json',report);return
    if args.arm=='exact':
        base=make_model();env.reset(seed=19)
        with torch.no_grad():
            torch.testing.assert_close(model.encode(env.grid,env.stats),base.encode(env.grid,env.stats),rtol=1e-5,atol=1e-6)
            exact=model.prepare(env.grid,env.stats)[1]
            assert torch.equal(exact[:,:4],categories(env.grid)) and torch.equal(exact[:,4:],(env.grid[:,4:6]>0).float())
        del base;report['initial_feature_parity']=True
    opt=torch.optim.Adam(model.parameters(),lr=1e-4);scaler=torch.amp.GradScaler('cuda',init_scale=1024)
    balanced=args.arm!='control';expert=Buffer(args.arm=='exact',balanced);learner=Buffer(args.arm=='exact',balanced)
    def assess(cls,split='validation'):
        with torch.random.fork_rng(devices=[0]):
            torch.manual_seed(11812);return evaluate(policy,split,env_class=cls,limit=1024)
    report['baseline']={} if args.smoke else assess(factory(1))
    torch.manual_seed(7321)
    start=time.monotonic();excluded=0.;decisions=0;examples=0;skips=0
    for j in range(1 if args.smoke else 4):decisions+=collect(env,expert,model,policy,1,11000+j)
    decisions+=collect(env,learner,model,policy,.1 if not balanced else 0,11050)
    best=-1
    for step in range(1,(1 if args.smoke else args.updates)+1):
        opt.zero_grad(set_to_none=True);a,na=expert.loss(model,execution);b,nb=learner.loss(model,execution);loss=(a+b)*.5
        assert torch.isfinite(loss)
        scale=scaler.get_scale();scaler.scale(loss).backward();scaler.unscale_(opt);torch.nn.utils.clip_grad_norm_(model.parameters(),1);scaler.step(opt);scaler.update();skips+=scaler.get_scale()<scale;examples+=na+nb
        if step%100==0:decisions+=collect(env,learner,model,policy,.1 if not balanced else 0,11000+step)
        if step%500==0:decisions+=collect(env,expert,model,policy,1,16000+step)
        if step%500==0 or step==args.updates or args.smoke:
            elapsed=time.monotonic()-start-excluded;t=time.monotonic();val={} if args.smoke else assess(factory(1));excluded+=time.monotonic()-t
            row=dict(step=step,training_seconds=elapsed,decisions=decisions,examples=examples,overflow_skips=skips,loss=float(loss.detach()),validation=val.get('summary',{}),expert=expert.coverage(),learner=learner.coverage());report['history'].append(row)
            score=0 if args.smoke else sum(v['exit'] for v in val['summary'].values())/2
            payload=dict(model=model.state_dict(),optimizer=opt.state_dict(),scaler=scaler.state_dict(),step=step,arm=args.arm)
            torch.save(payload,folder/'latest.pt')
            if score>best:best=score;report['selected']=row;torch.save(payload,folder/'selected.pt')
            save_json(folder/'progress.json',report);print(json.dumps(row),flush=True)
    report['training_seconds']=time.monotonic()-start-excluded
    model.load_state_dict(torch.load(folder/'selected.pt',weights_only=False)['model'])
    if not args.smoke:
        report['middle_test']=assess(factory(1),'test');report['full_test']=assess(FullEnv,'test');report['full_validation']=assess(FullEnv)
    report['finished']=True;save_json(ROOT/'results'/f'{name}.json',report);save_json(folder/'progress.json',report)
    print('FINISHED',name,flush=True)
if __name__=='__main__':main()
