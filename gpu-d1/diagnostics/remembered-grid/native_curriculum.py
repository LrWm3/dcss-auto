"""Native-scale sequence DAgger curriculum; no route hints in observations."""
import argparse, fcntl, hashlib, json, time
from pathlib import Path
import numpy as np
import torch
from torch.nn import functional as F
from fullsize_navigation import FullEnv, FOLDER, DIRS, build_full
from runtime import OUT, ROOT
from run import evaluate, save_json
from optimize_symbolic import load
from symbolic_execution import PolicyExecution, StaticInference

BANDS = [(4,12), (12,24), (24,128)]
SCENES = {}

def scenes(split, stage):
    key = (split,stage)
    if key in SCENES:return SCENES[key]
    cache = FOLDER / f'curriculum-{split}-{stage}.npy'
    if not cache.exists():
        lo,hi = BANDS[stage];rng = np.random.default_rng(62100+100*stage+['train','validation','test'].index(split))
        rows=[]
        with np.load(FOLDER/'maps'/f'{split}.npz') as packed:
            a={k:packed[k] for k in packed.files}
            for mid,n in enumerate(a['ncells']):
                cells=a['cells'][mid,:n];floor=a['floor'][mid];dist=a['distance'][a['offsets'][mid]:a['offsets'][mid]+n]
                for _ in range(4):
                    start=int(rng.integers(n));valid=np.where((dist[start,cells]>=lo)&(dist[start,cells]<=hi))[0]
                    assert len(valid)
                    goal=int(rng.choice(valid));player=int(cells[start]);current=int(cells[goal]);history=[current]
                    while current!=player:
                        x,y=current%80,current//80
                        options=[(y+dy)*80+x+dx for dx,dy in DIRS if 0<=x+dx<80 and 0<=y+dy<70]
                        current=next(q for q in options if floor[q] and dist[start,q]+1==dist[start,current]);history.append(current)
                    stairs=[int(cells[k]) for k in np.argsort(dist[goal,cells])[:3]]
                    for kind in (0,1):
                        hist=history if kind==0 else [player]
                        row=[mid,kind,player,*stairs,-1,len(hist),*hist];rows.append(row+[-1]*(264-len(row)))
        np.save(cache,np.array(rows,np.int32))
    SCENES[key]=torch.from_numpy(np.load(cache)).cuda()
    return SCENES[key]


def factory(stage):
    class CurriculumEnv(FullEnv):
        def __init__(self,split='train',batch=128):
            super().__init__(split,batch);self.scenes=scenes(split,stage)
    return CurriculumEnv


class Buffer:
    """Cache deterministic symbolic inputs, not trainable encoder features."""
    def __init__(self,capacity=1024):
        self.capacity=capacity;self.n=0;self.cursor=0
        self.p=[torch.empty(capacity,32,*shape,device='cuda') for shape in [(5,15,15),(6,16,16),(6,15,15),(2,)]]
        self.mask=torch.empty(capacity,32,19,device='cuda');self.label=torch.empty(capacity,32,device='cuda',dtype=torch.long);self.valid=torch.empty(capacity,32,device='cuda',dtype=torch.bool)
    def add(self,history):
        values=[torch.stack(x,1) for x in zip(*history)]
        ids=values[-1][:,16:].any(1).nonzero().flatten();n=len(ids)
        if not n:return
        assert n<=self.capacity
        ix=(torch.arange(n,device='cuda')+self.cursor)%self.capacity
        for dst,src in zip(self.p+[self.mask,self.label,self.valid],values):dst[ix]=src[ids]
        self.cursor=(self.cursor+n)%self.capacity;self.n=min(self.capacity,self.n+n)
    def loss(self,model,execution,batch=16):
        ix=torch.randint(self.n,(batch,),device='cuda');v=self.valid[ix]
        assert ((v[:,:16].all(1))|(~v[:,:16].any(1))).all()
        with torch.no_grad(),torch.autocast('cuda',dtype=torch.float16):
            x=execution.encode([p[ix,:16].flatten(0,1) for p in self.p]).reshape(batch,16,-1)
            _,h=model.sequence(x);h=h*v[:,15,None]
        with torch.autocast('cuda',dtype=torch.float16):
            x=execution.encode([p[ix,16:].flatten(0,1) for p in self.p]).reshape(batch,16,-1)
            z,_=model.sequence(x,h)
            logits=model.policy(z).float().masked_fill(self.mask[ix,16:]==0,-1e9)
        target=self.label[ix,16:];valid=v[:,16:]
        assert (self.mask[ix,16:].gather(-1,target[...,None]).squeeze(-1)[valid]>0).all()
        losses=F.cross_entropy(logits.flatten(0,1),target.flatten(),reduction='none').reshape(batch,16)
        return (losses*valid).sum()/valid.sum(),int(valid.sum())


@torch.no_grad()
def collect(env,buffer,model,policy,beta,seed,steps=512):
    env.reset(seed=seed);policy.reset_cache();history=[];decisions=0
    def snapshot():return (*[x.clone() for x in model.prepare(env.grid,env.stats)],env.mask.clone(),env.labels.clone(),env.active.clone())
    pad=list(snapshot());pad[-1]=torch.zeros_like(env.active);history=[tuple(pad)]*16
    for tick in range(steps):
        history.append(snapshot());decisions+=int(env.active.sum());action=env.labels.clone()
        assert (env.mask.gather(1,action[:,None]).squeeze()>0).all()
        if beta<1:
            predicted=policy(env.grid,env.mask,env.stats).argmax(-1)
            action=torch.where(torch.rand(env.batch,device='cuda')<beta,action,predicted)
        env.step(action,limit=1024)
        if (tick+1)%16==0:buffer.add(history[-32:]);history=history[-16:]
        if not env.active.any() or tick+1==steps:
            if (tick+1)%16:
                pad=list(snapshot());pad[-1]=torch.zeros_like(env.active)
                history.extend([tuple(pad)]*(16-(tick+1)%16));buffer.add(history[-32:])
            break
    return decisions


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--name',default='native-curriculum-seed0');ap.add_argument('--updates',type=int,default=2000);ap.add_argument('--smoke',action='store_true');args=ap.parse_args()
    torch.set_num_threads(1);torch.manual_seed(0);torch.backends.cudnn.benchmark=True;build_full()
    folder=OUT/args.name;folder.mkdir(exist_ok=True);lock=(folder/'run.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if (folder/'latest.pt').exists():raise RuntimeError('Refusing to overwrite checkpoints')
    source=OUT/'symbolic-ppo-durable-seed0/latest.pt'
    model=load(True).configure_encoder(True,True);model.load_state_dict(torch.load(source,weights_only=False)['model'])
    execution=PolicyExecution(model,compiled=True);policy=StaticInference(execution,amp=True,graphed=True)
    opt=torch.optim.Adam(model.parameters(),lr=1e-4);scaler=torch.amp.GradScaler('cuda')
    report=dict(manifest=dict(seed=0,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),bands=BANDS,max_updates_per_stage=args.updates,lr=1e-4,map_manifest_sha256=hashlib.sha256((FOLDER/'maps/manifest.json').read_bytes()).hexdigest(),deadline=1024,collection_cap=512,burn_in=16,learn_steps=16,batch_sequences_per_buffer=16,buffer_capacity=1024,scope='Native 80x70 maps, 15x15 local,16x16 global, no monsters. Sequence imitation/DAgger, not PPO; controller labels are targets only. No augmentation. Fixed split geometries; validation selects stage checkpoints. Distances define fixtures only.'),stages=[],training_seconds=0.,decisions=0,supervised_examples=0)
    def assess(env_class,split='validation'):
        with torch.random.fork_rng(devices=[0]):
            torch.manual_seed(11812)
            return evaluate(policy,split,env_class=env_class,limit=1024)
    if not args.smoke:report['baseline']=assess(FullEnv,'test')
    total_start=time.monotonic();excluded=0.;passed=True
    for stage in range(3):
        make_env=factory(stage);env=make_env('train',32);expert=Buffer();learner=Buffer();best=-1.;selected=None
        record=dict(stage=stage,band=BANDS[stage],history=[]);report['stages'].append(record)
        t=time.monotonic();base=assess(make_env) if not args.smoke else {};excluded+=time.monotonic()-t;record['baseline']=base
        for j in range(4 if not args.smoke else 1):report['decisions']+=collect(env,expert,model,policy,1,stage*10000+j)
        report['decisions']+=collect(env,learner,model,policy,.5,stage*10000+50)
        for step in range(1,(2 if args.smoke else args.updates)+1):
            opt.zero_grad(set_to_none=True);a,na=expert.loss(model,execution);b,nb=learner.loss(model,execution);loss=(a+b)*.5
            assert torch.isfinite(loss)
            scaler.scale(loss).backward();scaler.unscale_(opt);torch.nn.utils.clip_grad_norm_(model.parameters(),1);scaler.step(opt);scaler.update()
            report['supervised_examples']+=na+nb
            if step%100==0:
                report['decisions']+=collect(env,learner,model,policy,max(.1,.5-step/4000),stage*10000+step)
            if step%500==0:report['decisions']+=collect(env,expert,model,policy,1,stage*10000+step+5000)
            if step%500==0 or step==args.updates or args.smoke:
                trained=time.monotonic()-total_start-excluded;t=time.monotonic();validation=assess(make_env) if not args.smoke else {};excluded+=time.monotonic()-t
                row=dict(step=step,training_seconds=trained,decisions=report['decisions'],loss=float(loss.detach()),validation=validation.get('summary',{}));record['history'].append(row);print(json.dumps(dict(stage=stage,**row)),flush=True)
                if args.smoke:score=0.;passed=False
                else:
                    v=validation['summary'];score=(v['known_stairs']['exit']+v['exploration']['exit'])/2
                    passed=v['known_stairs']['exit']>=(.85 if stage==0 else .80) and v['exploration']['exit']>=(.75 if stage==0 else .65)
                payload=dict(model=model.state_dict(),optimizer=opt.state_dict(),scaler=scaler.state_dict(),stage=stage,step=step)
                torch.save(payload,folder/'latest.pt')
                if score>best or passed:
                    best=score;selected=row;torch.save(payload,folder/f'stage-{stage}-best.pt')
                save_json(folder/'progress.json',report)
                if passed or args.smoke:break
        record['passed']=passed;record['selected']=selected
        ck=torch.load(folder/f'stage-{stage}-best.pt',weights_only=False);model.load_state_dict(ck['model']);opt.load_state_dict(ck['optimizer']);scaler.load_state_dict(ck['scaler'])
        del expert,learner,env
        if not passed:break
    report['training_seconds']=time.monotonic()-total_start-excluded
    if not args.smoke:
        report['final_test']=assess(FullEnv,'test');report['final_validation']=assess(FullEnv)
        report['final_stage_test']=assess(factory(report['stages'][-1]['stage']),'test')
        report['erase_global_note']='Not evaluated in this initial curriculum screen.'
    torch.save(dict(model=model.state_dict(),selected=report['stages'][-1]['selected']),folder/'selected.pt')
    report['finished']=True;report['all_stages_passed']=passed and len(report['stages'])==3
    save_json(folder/'progress.json',report);save_json(ROOT/'results'/f'{args.name}.json',report)
    print('FINISHED',json.dumps({k:report[k] for k in ['training_seconds','decisions','supervised_examples','all_stages_passed']}),flush=True)
if __name__=='__main__':main()
