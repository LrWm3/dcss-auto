"""Bounded supervised/DAgger navigation demonstration, no runtime route hints."""
import argparse,json,time,shutil,hashlib,fcntl
import numpy as np
import torch
from torch.nn import functional as F
from runtime import OUT,HERE,Env,Policy,SpatialPolicy,PackedPolicy,Packed2Policy,CroppedSpatialPolicy,ThinSpatialPolicy,build

def save_json(path,x):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(x,indent=2));tmp.replace(path)

@torch.no_grad()
def evaluate(model,split='validation',limit=None,teacher=False,intervene=None,mode='greedy'):
    if limit is None:limit=512 if split=='long' else 256
    start=time.monotonic();proto=Env(split,1);n=len(proto.scenes);e=Env(split,128);rows=[]
    for offset in range(0,n,128):
        ids=torch.arange(offset,offset+128,device='cuda')%n;valid=min(128,n-offset);e.reset(ids,seed=812+offset,labels=teacher)
        if hasattr(model,'reset_cache'):model.reset_cache()
        initial=e.meta.clone();yy,xx=torch.meshgrid(torch.arange(32,device='cuda'),torch.arange(32,device='cuda'),indexing='ij');near=(xx[None]-e.stats[:,2,None,None]).abs().le(7)&(yy[None]-e.stats[:,3,None,None]).abs().le(7);far=(e.grid[:,4].sum((1,2))>0)&~((e.grid[:,4]>0)&near).any((1,2));terminal=torch.zeros(128,5,device='cuda');reversals=torch.zeros(128,device='cuda');pp=e.meta[:,0].clone();prev=pp.clone();woke=torch.zeros(128,device='cuda',dtype=torch.bool)
        for tick in range(limit):
            active=e.active.clone();p=e.meta[:,0].clone();woke|=active&e.meta[:,2].bool()
            if teacher:a=e.labels.clone()
            else:
                logits=model(e.grid,e.mask,e.stats,intervene);a=logits.argmax(-1) if mode=='greedy' else torch.distributions.Categorical(logits=logits).sample()
            assert (e.mask.gather(1,a[:,None]).squeeze()>0).all()
            e.step(a,limit=limit,labels=teacher)
            reversals+=active&(e.meta[:,0]==pp)&(p!=pp);pp=p;prev=e.meta[:,0].clone()
            end=active&~e.active;terminal[end]=e.out[end][:,[2,6,7,5,3]]
            if not e.active.any():break
        assert not e.active.any()
        for j in range(valid):
            rows.append(dict(goal_outside_local=bool(far[j]),initial_known_stairs=int(initial[j,1]),scenario=int(ids[j]),kind=int(e.scenes[ids[j],1]),map=int(e.scenes[ids[j],0]),exit=int(terminal[j,0]),death=int(terminal[j,1]),timeout=int(terminal[j,2]),turns=float(terminal[j,3]-initial[j,5]),kills=float(terminal[j,4]),reversals=int(reversals[j]),woke=bool(woke[j])))
    summary={}
    for k,name in enumerate(['known_stairs','exploration','threat_backtrack']):
        rs=[r for r in rows if r['kind']==k];summary[name]={key:float(np.mean([r[key] for r in rs])) for key in ['exit','death','timeout','turns','kills','reversals','woke']};summary[name]['episodes']=len(rs)
    far_rows=[r for r in rows if r['kind']==0 and r['goal_outside_local']]
    return dict(deadline=limit,summary=summary,known_stairs_outside_crop=dict(episodes=len(far_rows),exit=float(np.mean([r['exit'] for r in far_rows])) if far_rows else None),rows=rows,seconds=time.monotonic()-start)

class Buffer:
    def __init__(self,capacity=32768):
        self.capacity=capacity;self.n=0;self.cursor=0
        self.g=torch.empty(capacity,11,32,32,device='cuda',dtype=torch.uint8);self.m=torch.empty(capacity,19,device='cuda');self.s=torch.empty(capacity,4,device='cuda');self.y=torch.empty(capacity,device='cuda',dtype=torch.long)
    def add(self,e):
        ix=torch.where(e.active)[0];n=len(ix);dest=(torch.arange(n,device='cuda')+self.cursor)%self.capacity
        self.g[dest]=e.grid[ix];self.m[dest]=e.mask[ix];self.s[dest]=e.stats[ix];self.y[dest]=e.labels[ix];self.cursor=(self.cursor+n)%self.capacity;self.n=min(self.capacity,self.n+n)
    def loss(self,model,batch=128):
        ix=torch.randint(self.n,(batch,),device='cuda');g=self.g[ix];m=self.m[ix];stats=self.s[ix].clone();y=self.y[ix]
        # Rotate/reflect the entire observation and joint directional action.
        group=int(torch.randint(8,()).item());directions=[(0,-1),(1,0),(0,1),(-1,0),(1,-1),(1,1),(-1,1),(-1,-1)];permutation=[]
        for dx,dy in directions:
            if group>=4:dx=-dx
            for _ in range(group%4):dx,dy=dy,-dx
            permutation.append(directions.index((dx,dy)))
        permutation=torch.tensor(permutation+[8+x for x in permutation]+[16,17,18],device='cuda')
        if group>=4:g=g.flip(-1)
        g=torch.rot90(g,group%4,(-2,-1));mm=torch.empty_like(m);mm[:,permutation]=m;y=permutation[y]
        pos=g[:,5].flatten(1).argmax(1);stats[:,2]=pos%32;stats[:,3]=pos//32
        logits=model(g,mm,stats);return F.cross_entropy(logits,y)

@torch.no_grad()
def collect(e,b,model=None,kinds=(0,1,2),beta=1,steps=128):
    e.reset(kinds=kinds,seed=int(torch.randint(1000000,()).item()));decisions=0
    for tick in range(steps):
        assert (e.mask.gather(1,e.labels[:,None]).squeeze()>0).all()
        b.add(e);decisions+=int(e.active.sum());a=e.labels.clone()
        if model is not None:
            learner=model(e.grid,e.mask,e.stats).argmax(-1);a=torch.where(torch.rand(e.batch,device='cuda')<beta,a,learner)
        e.step(a,limit=256)
        if not e.active.any():break
    return decisions

def main():
    p=argparse.ArgumentParser();p.add_argument('--arm',choices=['memory','terrain','local'],default='memory');p.add_argument('--architecture',choices=['conv','spatial','packed','packed2','cropped','thin','cached','attn','coarse','counts'],default='conv');p.add_argument('--updates',type=int,default=3000);p.add_argument('--resume',action='store_true');p.add_argument('--evaluate',action='store_true');p.add_argument('--preflight',action='store_true');p.add_argument('--compile',action='store_true');args=p.parse_args()
    if args.architecture in ('cached','attn','coarse','counts') and args.arm!='terrain':p.error('cached currently supports only --arm terrain')
    torch.set_num_threads(1);torch.manual_seed(0);torch.backends.cudnn.benchmark=True
    if shutil.disk_usage(HERE).free<10*1024**3:raise RuntimeError('Need 10GiB free')
    build();folder=OUT/(args.arm if args.architecture=='conv' else args.arm+'-'+args.architecture);folder.mkdir(exist_ok=True)
    lock=(folder/'training.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    from cached_policy import CachedMapPolicy
    from compact_policy import CompactPolicy
    model=CompactPolicy(args.architecture).cuda() if args.architecture in ('attn','coarse','counts') else CachedMapPolicy().cuda() if args.architecture=='cached' else {'conv':Policy,'spatial':SpatialPolicy,'packed':PackedPolicy,'packed2':Packed2Policy,'cropped':CroppedSpatialPolicy,'thin':ThinSpatialPolicy}[args.architecture](args.arm).cuda();
    if args.architecture in ('packed','packed2','cropped','thin'):model.to(memory_format=torch.channels_last)
    scaler=torch.amp.GradScaler('cuda',enabled=args.architecture in ('packed','packed2','cropped','thin'))
    optimizer=torch.optim.Adam(model.parameters(),lr=.0003);start_step=0;decisions=0
    if args.resume or args.evaluate:
        ck=torch.load(folder/('best.pt' if args.evaluate and (folder/'best.pt').exists() else 'latest.pt'),weights_only=False);model.load_state_dict(ck['model']);optimizer.load_state_dict(ck['optimizer']);start_step=ck['step'];decisions=ck['decisions']
        if 'scaler' in ck:scaler.load_state_dict(ck['scaler'])
    if args.compile:
        if hasattr(model,'fast_pool'):model.fast_pool=True
        model.compile(fullgraph=True)
    if args.preflight:
        result=evaluate(model,teacher=True);save_json(OUT/'preflight.json',result);print('teacher',result['summary'],flush=True);return
    if args.evaluate:
        report={}
        for split in ['test','long']:
            for mode in ['greedy','sampled']:
                z=evaluate(model,split,mode=mode);report[split+'_'+mode]=z;print(split,mode,z['summary'],flush=True);save_json(folder/'test.json',report)
        return
    manifest=dict(compiled=args.compile,seed=0,arm=args.arm,architecture=args.architecture,updates=args.updates,resume=args.resume,source_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in HERE.glob('*.py')},native=json.loads((OUT/'build.json').read_text()),map_manifest_sha256=hashlib.sha256((OUT/'maps/manifest.json').read_bytes()).hexdigest())
    save_json(folder/('resume-manifest.json' if args.resume else 'manifest.json'),manifest)
    buffer=Buffer();expert=Buffer(65536);e=Env();t0=time.monotonic();history=json.loads((folder/'training.json').read_text()) if args.resume else [];prior_seconds=history[-1]['training_seconds'] if history else 0;best=max([sum(v['exit'] for v in h['validation'].values())/3 for h in history],default=-1)
    for _ in range(16):decisions+=collect(e,expert,kinds=(0,1,2))
    decisions+=collect(e,buffer,kinds=(0,1,2))
    print('buffer',buffer.n,'decisions',decisions,flush=True)
    for step in range(start_step+1,args.updates+1):
        optimizer.zero_grad(set_to_none=True);loss=.5*(buffer.loss(model)+expert.loss(model));scaler.scale(loss).backward();scaler.unscale_(optimizer);torch.nn.utils.clip_grad_norm_(model.parameters(),1);scaler.step(optimizer);scaler.update()
        if step%500==0:print('progress',step,'seconds',round(time.monotonic()-t0,1),'loss_scale',scaler.get_scale(),flush=True)
        if step%100==0:
            decisions+=collect(e,buffer,model,beta=max(.1,.8-step/5000))
        if step%500==0:decisions+=collect(e,expert)
        if step%2000==0 or step==args.updates:
            torch.cuda.synchronize();trained=prior_seconds+time.monotonic()-t0
            result=evaluate(model);record=dict(step=step,supervised_examples=step*256,decisions=decisions,training_seconds=trained,loss=float(loss),validation=result['summary']);history.append(record);print(json.dumps(record),flush=True)
            torch.save(dict(model=model.state_dict(),optimizer=optimizer.state_dict(),scaler=scaler.state_dict(),step=step,decisions=decisions,arm=args.arm,architecture=args.architecture),folder/'latest.tmp');(folder/'latest.tmp').replace(folder/'latest.pt')
            score=sum(v['exit'] for v in result['summary'].values())/3
            if score>best:
                best=score;shutil.copyfile(folder/'latest.pt',folder/'best.tmp');(folder/'best.tmp').replace(folder/'best.pt');save_json(folder/'selection.json',record)
            save_json(folder/'training.json',history);t0+=result['seconds']
if __name__=='__main__':main()
