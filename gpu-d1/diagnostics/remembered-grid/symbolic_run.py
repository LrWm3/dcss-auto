"""Sequence-preserving supervised/DAgger screen, 16 burn-in + 16 learning steps."""
import argparse,fcntl,hashlib,json,shutil,time
from pathlib import Path
import torch
from torch.nn import functional as F
from run import evaluate,save_json
from runtime import Env,OUT,ROOT,HERE,build
from symbolic_policy import SymbolicPolicy,Stateful

class Sequences:
    def __init__(self,capacity=1024):
        self.capacity=capacity;self.n=0;self.cursor=0
        self.g=torch.empty(capacity,32,11,32,32,device='cuda',dtype=torch.uint8)
        self.m=torch.empty(capacity,32,19,device='cuda');self.s=torch.empty(capacity,32,4,device='cuda')
        self.y=torch.empty(capacity,32,device='cuda',dtype=torch.long);self.v=torch.empty(capacity,32,device='cuda',dtype=torch.bool)
    def add(self,states):
        # states = chronological snapshots, initially padded with invalid history.
        tensors=[torch.stack([x[j] for x in states],1) for j in range(5)]
        ids=tensors[4][:,16:].any(1).nonzero().flatten();n=len(ids)
        ix=(torch.arange(n,device='cuda')+self.cursor)%self.capacity
        for dst,src in zip([self.g,self.m,self.s,self.y,self.v],tensors):dst[ix]=src[ids]
        self.cursor=(self.cursor+n)%self.capacity;self.n=min(self.capacity,self.n+n)
    def loss(self,model,batch=8):
        ix=torch.randint(self.n,(batch,),device='cuda');g=self.g[ix];m=self.m[ix];s=self.s[ix].clone();y=self.y[ix];v=self.v[ix]
        group=int(torch.randint(8,()).item());dirs=[(0,-1),(1,0),(0,1),(-1,0),(1,-1),(1,1),(-1,1),(-1,-1)];perm=[]
        for dx,dy in dirs:
            if group>=4:dx=-dx
            for _ in range(group%4):dx,dy=dy,-dx
            perm.append(dirs.index((dx,dy)))
        perm=torch.tensor(perm+[8+x for x in perm]+[16,17,18],device='cuda')
        if group>=4:g=g.flip(-1)
        g=torch.rot90(g,group%4,(-2,-1));mm=torch.empty_like(m);mm[:,:,perm]=m;m=mm;y=perm[y]
        pos=g[:,:,5].flatten(2).argmax(2);s[:,:,2]=pos%32;s[:,:,3]=pos//32
        h=None
        if model.recurrent:
            with torch.no_grad():
                x=model.encode(g[:,:16].reshape(-1,11,32,32),s[:,:16].reshape(-1,4)).reshape(batch,16,-1)
                if hasattr(model,'sequence'):
                    # Stored burn-in is either all valid or the initial all-invalid prefix.
                    _,h=model.sequence(x);h=h*v[:,15,None]
                else:
                    h=x.new_zeros(batch,128)
                    for t in range(16):
                        _,new=model.step_features(x[:,t],m[:,t],h);h=torch.where(v[:,t,None],new,h)
        x=model.encode(g[:,16:].reshape(-1,11,32,32),s[:,16:].reshape(-1,4)).reshape(batch,16,-1)
        if model.recurrent and hasattr(model,'sequence'):
            # Learning padding is a terminal suffix; it cannot influence valid earlier outputs.
            z,_=model.sequence(x,h);logits=model.policy(z).float().masked_fill(m[:,16:]==0,-1e9).reshape(-1,19)
        elif model.recurrent:
            logits=[]
            for t in range(16):
                z,new=model.step_features(x[:,t],m[:,t+16],h)
                h=torch.where(v[:,t+16,None],new,h);logits.append(z)
            logits=torch.stack(logits,1).reshape(-1,19)
        else:logits=model.step_features(x.reshape(-1,194),m[:,16:].reshape(-1,19))[0]
        losses=F.cross_entropy(logits,y[:,16:].reshape(-1),reduction='none').reshape(batch,16)
        valid=v[:,16:];return (losses*valid).sum()/valid.sum(),int(valid.sum())

@torch.no_grad()
def collect(e,buffer,model=None,beta=1,steps=128):
    e.reset(seed=int(torch.randint(1000000,()).item()));history=[];policy=Stateful(model) if model is not None else None;decisions=0
    def snapshot():return (e.grid.clone(),e.mask.clone(),e.stats.clone(),e.labels.clone(),e.active.clone())
    pad=list(snapshot());pad[4]=torch.zeros_like(e.active);history=[tuple(pad)]*16
    for tick in range(steps):
        history.append(snapshot());decisions+=int(e.active.sum())
        action=e.labels.clone()
        if policy is not None:
            learner=policy(e.grid,e.mask,e.stats).argmax(-1);action=torch.where(torch.rand(e.batch,device='cuda')<beta,action,learner)
        e.step(action,limit=256)
        if (tick+1)%16==0:
            buffer.add(history[-32:]);history=history[-16:]
        if not e.active.any() or tick+1==steps:
            if (tick+1)%16:
                pad=list(snapshot());pad[4]=torch.zeros_like(e.active)
                history += [tuple(pad)]*(16-(tick+1)%16);buffer.add(history[-32:])
            break
    return decisions

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--kind',choices=['ff','gru','mingru'],required=True);ap.add_argument('--updates',type=int,default=12000);ap.add_argument('--fast',action='store_true');ap.add_argument('--scan-backend',choices=['eager','triton'],default='eager');ap.add_argument('--encoder-fast',action='store_true');args=ap.parse_args()
    if args.scan_backend!='eager' and args.kind!='mingru':ap.error('--scan-backend triton requires --kind mingru')
    if args.encoder_fast and not (args.fast or args.kind=='mingru'):ap.error('--encoder-fast requires --fast or --kind mingru')
    suffix=('-fast' if args.fast else '')+('-triton' if args.scan_backend=='triton' else '')+('-encoder' if args.encoder_fast else '')
    torch.set_num_threads(1);torch.manual_seed(0);torch.backends.cudnn.benchmark=True
    build();folder=OUT/('symbolic-'+args.kind+suffix);folder.mkdir(exist_ok=True)
    lock=(folder/'training.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if (folder/'latest.pt').exists():raise RuntimeError('Refusing to overwrite existing training')
    from symbolic_fast import FastSymbolicPolicy
    from symbolic_mingru import MinSymbolicPolicy
    model=(MinSymbolicPolicy(args.scan_backend) if args.kind=='mingru' else FastSymbolicPolicy(args.kind=='gru') if args.fast else SymbolicPolicy(args.kind=='gru')).cuda()
    if args.encoder_fast:model.configure_encoder(True,True)
    opt=torch.optim.Adam(model.parameters(),lr=.0003)
    save_json(folder/'manifest.json',dict(kind=args.kind,fast=args.fast,encoder_fast=args.encoder_fast,scan_backend=args.scan_backend,seed=0,updates=args.updates,burn_in=16,learning_length=16,sequences_per_buffer=1024,batch_per_buffer=8,source_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [HERE/'symbolic_policy.py',Path(__file__)]+([HERE/'symbolic_fast.py'] if args.fast or args.kind=='mingru' else [])+([HERE/'symbolic_mingru.py'] if args.kind=='mingru' else [])+([HERE/'mingru_scan.py'] if args.scan_backend=='triton' else [])},maps=hashlib.sha256((OUT/'maps/manifest.json').read_bytes()).hexdigest()))
    expert=Sequences();learner=Sequences();e=Env(batch=64);decisions=0;examples=0;history=[];best=-1;t0=time.monotonic()
    for _ in range(16):decisions+=collect(e,expert)
    decisions+=collect(e,learner)
    for step in range(1,args.updates+1):
        opt.zero_grad(set_to_none=True);a,na=expert.loss(model);b,nb=learner.loss(model);loss=(a+b)*.5;loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),1);opt.step();examples+=na+nb
        if step%100==0:decisions+=collect(e,learner,model,beta=max(.1,.8-step/5000))
        if step%500==0:
            decisions+=collect(e,expert);print('progress',step,'seconds',round(time.monotonic()-t0,1),flush=True)
        if step%2000==0 or step==args.updates:
            seconds=time.monotonic()-t0;result=evaluate(Stateful(model));row=dict(step=step,supervised_examples=examples,decisions=decisions,training_seconds=seconds,loss=float(loss),validation=result['summary']);history.append(row);print(json.dumps(row),flush=True)
            torch.save(dict(model=model.state_dict(),optimizer=opt.state_dict(),step=step,kind=args.kind),folder/'latest.pt')
            score=sum(v['exit'] for v in result['summary'].values())/3
            if score>best:best=score;shutil.copyfile(folder/'latest.pt',folder/'best.pt');save_json(folder/'selection.json',row)
            save_json(folder/'training.json',history);t0+=result['seconds']
    model.load_state_dict(torch.load(folder/'best.pt',weights_only=False)['model']);report=dict(kind=args.kind,training=history,selected=json.loads((folder/'selection.json').read_text()),scope='Synthetic navigation; sequence supervised/DAgger, not PPO. 15x15 local, 16x16 symbolic global. Padding excluded from supervised sample counts.')
    for split,mode in [('test','greedy'),('long','greedy'),('test','sampled')]:
        torch.manual_seed(11812);r=evaluate(Stateful(model),split,mode=mode);report[split+'_'+mode]=r;print(split,mode,r['summary'],flush=True)
    if args.kind in ('gru','mingru'):report['reset_memory_test']=evaluate(Stateful(model,True),'test')
    save_json(ROOT/'results'/('remembered-grid-symbolic-'+args.kind+suffix+'.json'),report)

if __name__=='__main__':main()
