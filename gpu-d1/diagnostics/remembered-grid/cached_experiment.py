"""Quality, full-map compute, and real frozen-encoder PPO tests."""
import argparse,json,time,subprocess,os,hashlib
from pathlib import Path
import torch
from run import evaluate,save_json
from runtime import OUT,ROOT,Env
from cached_policy import CachedMapPolicy,FeatureCache
import probes

FOLDER=OUT/'terrain-cached'
def provenance():
    return dict(source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),Path(__file__).with_name('cached_policy.py'),Path(__file__).with_name('runtime.py')]},checkpoint_sha256=hashlib.sha256((FOLDER/'best.pt').read_bytes()).hexdigest(),map_manifest_sha256=hashlib.sha256((OUT/'maps/manifest.json').read_bytes()).hexdigest())
def load():
    m=CachedMapPolicy().cuda();ck=torch.load(FOLDER/'best.pt',weights_only=False);m.load_state_dict(ck['model'])
    # Supervision used fresh maps only, so this input never trained. Remove its
    # arbitrary initialized contribution when evaluating stale-map robustness.
    with torch.no_grad():m.actor.shared[0].weight[:,-1].zero_()
    return m,ck

def cached_eval(m,interval,split='validation',mode='greedy'):
    cache=FeatureCache(m,interval);z=evaluate(cache,split,mode=mode)
    z['cache']=dict(refreshes=cache.total_refreshes,encoded_slots_including_bucketing=cache.total_encoded_slots,observation_slots=cache.total_observations,refresh_fraction=cache.total_refreshes/cache.total_observations)
    return z

def quality():
    m,ck=load();result={'selected_update':ck['step'],'age_weight_zeroed':True,'validation':{},'heldout':{}}
    for interval in [1,4,8]:
        z=cached_eval(m,interval);result['validation'][str(interval)]=z
        print('validation',interval,z['summary'],flush=True)
    scores={k:sum(v['exit'] for v in z['summary'].values())/3 for k,z in result['validation'].items()}
    # Prefer the longest cache interval within one percentage point of best.
    interval=max(int(k) for k,v in scores.items() if v>=max(scores.values())-.01)
    result['selected_interval']=interval
    for split in ['test','long']:
        for i in [1,4,8]:
            z=cached_eval(m,i,split);result['heldout'][f'{split}_interval{i}']=z
            print(split,i,z['summary'],flush=True)
    probes.generate()
    result['paired_goals']=probes.evaluate(FeatureCache(m,interval))
    result['paired_goals_erased']=probes.evaluate(FeatureCache(m,interval),intervene='erase_global')
    result['sampled']=cached_eval(m,interval,'test',mode='sampled')
    result['provenance']=provenance();save_json(FOLDER/'quality.json',result);save_json(ROOT/'results/remembered-grid-cached-quality.json',result)

def benchmark(iterations=30):
    other=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,process_name','--format=csv,noheader'],text=True).strip().splitlines()
    other=[x for x in other if x.split(',')[0].strip()!=str(os.getpid())]
    if other:raise RuntimeError('Refusing contended benchmark: '+str(other))
    m,_=load();m.amp=True;m.to(memory_format=torch.channels_last);m.encoder.requires_grad_(False)
    warm=[]
    def timed(fn):
        torch.cuda.synchronize();start=time.perf_counter()
        for _ in range(10):fn()
        torch.cuda.synchronize();warm.append(time.perf_counter()-start);start=time.perf_counter()
        for _ in range(iterations):fn()
        torch.cuda.synchronize();return (time.perf_counter()-start)/iterations
    terrain=torch.randint(0,256,(512,3,70,80),device='cuda',dtype=torch.uint8)
    @torch.no_grad()
    def encode():
        with torch.autocast('cuda',dtype=torch.float16):return m.encoder(terrain)
    encoder=timed(encode);features=encode();grid=torch.randint(0,256,(512,11,70,80),device='cuda',dtype=torch.uint8);stats=torch.tensor([1.,.1,40.,35.],device='cuda').repeat(512,1);mask=torch.ones(512,19,device='cuda')
    @torch.no_grad()
    def infer():
        args=m.inputs(grid,stats,features)
        with torch.autocast('cuda',dtype=torch.float16):logits,v=m.actor(*args,mask)
        return torch.distributions.Categorical(logits=logits).sample(),v
    inference=timed(infer)
    local,query,scalars=m.inputs(grid,stats,features);local=local.to(torch.uint8).repeat(2,1,1,1);query=query.half().repeat(2,1);scalars=scalars.repeat(2,1);mask=mask.repeat(2,1)
    opt=torch.optim.Adam(m.actor.parameters(),lr=1e-5);scaler=torch.amp.GradScaler('cuda')
    with torch.no_grad(),torch.autocast('cuda',dtype=torch.float16):
        logits,oldv=m.actor(local,query,scalars,mask);d=torch.distributions.Categorical(logits=logits);a=d.sample();lp=d.log_prob(a);adv=torch.randn_like(oldv);ret=oldv+adv
    def train():
        opt.zero_grad(set_to_none=True)
        with torch.autocast('cuda',dtype=torch.float16):logits,v=m.actor(local,query,scalars,mask)
        d=torch.distributions.Categorical(logits=logits);ratio=(d.log_prob(a)-lp).exp();loss=-torch.minimum(ratio*adv,ratio.clamp(.8,1.2)*adv).mean()+.25*(v-ret).square().mean()-.001*d.entropy().mean()
        scaler.scale(loss).backward();scaler.unscale_(opt);torch.nn.utils.clip_grad_norm_(m.actor.parameters(),.5);scaler.step(opt);scaler.update()
    training=timed(train)
    result=dict(scope='Synthetic full-map network cost, not end-to-end PPO. Includes local/query extraction, action sampling, optimizer/clipping/scaling; excludes simulator, cache change detection, storage and GAE.',device=torch.cuda.get_device_name(),map_shape=[70,80],amp=True,inference_batch=512,training_batch=1024,encoder_ms=encoder*1000,actor_inference_ms=inference*1000,actor_training_ms=training*1000,warmup_seconds=warm,network_only_four_epoch_decisions_per_second={str(i):1/(inference/512+encoder/512/i+4*training/1024) for i in [1,4,8]},cached_feature_bytes_per_world=16*70*80*2,replay_input_bytes_per_decision=11*15*15+144*2+3*4+19*4,source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    result['provenance']=provenance();print(json.dumps(result),flush=True);save_json(ROOT/'results/remembered-grid-cached-performance.json',result)

def ppo(target=250000):
    m,ck=load();m.encoder.requires_grad_(False)
    interval=json.loads((FOLDER/'quality.json').read_text())['selected_interval'];cache=FeatureCache(m,interval)
    opt=torch.optim.Adam(m.actor.parameters(),lr=3e-5);torch.manual_seed(314)
    before={k:v.clone() for k,v in m.encoder.state_dict().items()};history=[]
    baseline=evaluate(cache,'validation');start=time.monotonic();decisions=0;waves=0;refreshes=0;slots=0
    e=Env('train',128)
    while decisions<target:
        e.reset(seed=314+waves,labels=False);cache.reset_cache();roll=[]
        with torch.no_grad():
            for t in range(256):
                active=e.active.clone();local,query,scalars=cache.prepare(e.grid,e.stats);query=query.half().float();mask=e.mask.clone();logits,v=m.actor(local,query,scalars,mask);d=torch.distributions.Categorical(logits=logits);a=d.sample();lp=d.log_prob(a)
                e.step(a,limit=256,labels=False);done=active&~e.active;reward=(e.out[:,2]-e.out[:,6])*done
                roll.append((local.to(torch.uint8),query.half(),scalars,mask,a,lp,v,reward,done,active))
                decisions+=int(active.sum())
                if not e.active.any():break
        refreshes+=cache.refreshes;slots+=cache.observations
        data=[torch.stack(x) for x in zip(*roll)];local,query,scalars,mask,a,lp,v,reward,done,active=data
        adv=torch.zeros_like(v);gae=torch.zeros(e.batch,device='cuda');nextv=torch.zeros_like(gae)
        for t in reversed(range(len(roll))):
            delta=reward[t]+.999*nextv*(~done[t])-v[t]
            gae=(delta+.999*.95*(~done[t])*gae)*active[t];adv[t]=gae;nextv=v[t]*active[t]
        ret=adv+v;sel=active.flatten();flat=lambda x:x.flatten(0,1)[sel]
        local,query,scalars,mask,a,lp,v,adv,ret=map(flat,[local,query,scalars,mask,a,lp,v,adv,ret]);adv=(adv-adv.mean())/(adv.std()+1e-8);n=len(a)
        losses=[];kls=[]
        for epoch in range(4):
            for ix in torch.randperm(n,device='cuda').split(1024):
                opt.zero_grad(set_to_none=True);logits,value=m.actor(local[ix],query[ix].float(),scalars[ix],mask[ix]);d=torch.distributions.Categorical(logits=logits);logratio=d.log_prob(a[ix])-lp[ix];ratio=logratio.exp()
                loss=-torch.minimum(ratio*adv[ix],ratio.clamp(.8,1.2)*adv[ix]).mean()+.25*(value-ret[ix]).square().mean()-.001*d.entropy().mean();loss.backward();torch.nn.utils.clip_grad_norm_(m.actor.parameters(),.5);opt.step()
                losses.append(float(loss.detach()));kls.append(float(((ratio-1)-logratio).mean().detach()))
        waves+=1;torch.cuda.synchronize();elapsed=time.monotonic()-start
        row=dict(wave=waves,decisions=decisions,training_seconds=elapsed,decisions_per_second=decisions/elapsed,cache_refresh_fraction=refreshes/slots,active_slot_fraction=decisions/slots,training_exit=float((reward==1).sum()/e.batch),loss=sum(losses)/len(losses),approx_kl=sum(kls)/len(kls));history.append(row);print(json.dumps(row),flush=True)
    assert all(torch.equal(v,before[k]) for k,v in m.encoder.state_dict().items())
    end=evaluate(cache,'validation');test=evaluate(cache,'test');sampled=evaluate(cache,'test',mode='sampled')
    result=dict(scope='Actual 32x32 synthetic navigation PPO; synchronous episode waves, only active decisions counted. No BC anchor; frozen map encoder. Not a full-size Crawl quality test.',source_update=ck['step'],seed=314,interval=interval,rewards=dict(exit=1,death=-1,timeout=0),gamma=.999,gae_lambda=.95,lr=3e-5,epochs=4,baseline_validation=baseline,final_validation=end,test_greedy=test,test_sampled=sampled,history=history,encoder_unchanged=True)
    result['provenance']=provenance();torch.save(dict(model=m.state_dict(),decisions=decisions,interval=interval),FOLDER/'ppo.pt');save_json(FOLDER/'ppo.json',result);save_json(ROOT/'results/remembered-grid-cached-ppo.json',result)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['quality','benchmark','ppo']);ap.add_argument('--decisions',type=int,default=250000);args=ap.parse_args()
    torch.set_num_threads(1);torch.manual_seed(991);torch.backends.cudnn.benchmark=True
    if args.mode=='quality':quality()
    elif args.mode=='benchmark':benchmark()
    else:ppo(args.decisions)
if __name__=='__main__':main()
