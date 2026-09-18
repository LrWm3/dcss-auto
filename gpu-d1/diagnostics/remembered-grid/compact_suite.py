"""Sequential equal-budget representation screen and uncontended compute tests."""
import argparse,hashlib,json,os,subprocess,time
from pathlib import Path
import torch
from run import evaluate,save_json
from runtime import OUT,ROOT,Env,HERE
from compact_policy import CompactPolicy,ExactCache
import probes

KINDS=['attn','coarse','counts','counts2','count_edges']
def provenance(kind):
    folder=OUT/('terrain-'+kind)
    return dict(seed=0,selected_update=json.loads((folder/'selection.json').read_text())['step'],training=json.loads((folder/'training.json').read_text()),source_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),HERE/'compact_policy.py',HERE/'run.py']},checkpoint_sha256=hashlib.sha256((folder/'best.pt').read_bytes()).hexdigest(),map_manifest_sha256=hashlib.sha256((OUT/'maps/manifest.json').read_bytes()).hexdigest())
def load(kind,amp=False):
    m=CompactPolicy(kind,amp).cuda();m.load_state_dict(torch.load(OUT/('terrain-'+kind)/'best.pt',weights_only=False)['model']);return m

def quality(kind):
    torch.manual_seed(991);m=load(kind);result={'kind':kind,'provenance':provenance(kind),'scope':'Existing 32x32 synthetic regression maps, no stale cache, one training seed. No PPO finetuning.'}
    for split,mode in [('test','greedy'),('long','greedy'),('test','sampled')]:
        torch.manual_seed(11812);z=evaluate(ExactCache(m),split,mode=mode);result[split+'_'+mode]=z
        print(kind,split,mode,z['summary'],flush=True)
    probes.generate();result['paired']=probes.evaluate(ExactCache(m));result['paired_erased']=probes.evaluate(ExactCache(m),intervene='erase_global')
    save_json(ROOT/'results'/f'remembered-grid-compact-{kind}.json',result)
    return result

def benchmark(kind,iterations=30):
    torch.manual_seed(991);train_batch=1024
    other=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,process_name','--format=csv,noheader'],text=True).strip().splitlines();other=[x for x in other if x.split(',')[0].strip()!=str(os.getpid())]
    if other:raise RuntimeError('Refusing contended benchmark: '+str(other))
    m=load(kind,True).to(memory_format=torch.channels_last);warm=[]
    def inputs(n):
        g=torch.zeros(n,11,70,80,device='cuda',dtype=torch.uint8);r=torch.randint(0,3,(n,70,80),device='cuda');g[:,0]=(r==1).byte()*255;g[:,1]=(r==2).byte()*255;g[:,3]=255;g[:,4,10,10]=255
        return g,torch.ones(n,19,device='cuda'),torch.tensor([1.,.1,40.,35.],device='cuda').repeat(n,1)
    def timed(fn):
        torch.cuda.synchronize();start=time.perf_counter()
        for _ in range(10):fn()
        torch.cuda.synchronize();warm.append(time.perf_counter()-start);start=time.perf_counter()
        for _ in range(iterations):fn()
        torch.cuda.synchronize();return (time.perf_counter()-start)/iterations
    g,mask,s=inputs(512)
    @torch.no_grad()
    def encode():
        with torch.autocast('cuda',dtype=torch.float16):return m.encode_map(m.terrain(g))
    enc=timed(encode);memory=encode()
    @torch.no_grad()
    def infer():
        with torch.autocast('cuda',dtype=torch.float16):logits,value=m.read_map(g,mask,s,memory,critic=True)
        return torch.distributions.Categorical(logits=logits).sample(),value
    inf=timed(infer);memory_bytes=memory.numel()*memory.element_size()//512
    del g,mask,s,memory
    rows=[]
    for frozen in [False,True]:
        m=load(kind,True).to(memory_format=torch.channels_last);m.encoder.requires_grad_(not frozen);g,mask,s=inputs(train_batch)
        with torch.no_grad(),torch.autocast('cuda',dtype=torch.float16):
            memory=m.encode_map(m.terrain(g));logits,oldv=m.read_map(g,mask,s,memory,critic=True);d=torch.distributions.Categorical(logits=logits);a=d.sample();lp=d.log_prob(a);adv=torch.randn_like(oldv);ret=oldv+adv
        opt=torch.optim.Adam([p for p in m.parameters() if p.requires_grad],lr=1e-5);scaler=torch.amp.GradScaler('cuda')
        def train():
            opt.zero_grad(set_to_none=True)
            with torch.autocast('cuda',dtype=torch.float16):
                current=memory if frozen else m.encode_map(m.terrain(g));logits,v=m.read_map(g,mask,s,current,critic=True)
            d=torch.distributions.Categorical(logits=logits);ratio=(d.log_prob(a)-lp).exp();loss=-torch.minimum(ratio*adv,ratio.clamp(.8,1.2)*adv).mean()+.25*(v-ret).square().mean()-.001*d.entropy().mean()
            scaler.scale(loss).backward();scaler.unscale_(opt);torch.nn.utils.clip_grad_norm_(m.parameters(),.5);scaler.step(opt);scaler.update()
        sec=timed(train);assert all(torch.isfinite(p).all() for p in m.parameters())
        rows.append(dict(frozen_encoder=frozen,training_ms=sec*1000,network_only_four_epoch_decisions_per_second={str(i):1/(inf/512+enc/512/i+4*sec/train_batch) for i in [1,4,8]}))
    # Check AMP navigation, since compute numbers use AMP but training was FP32.
    m=load(kind,True).to(memory_format=torch.channels_last);regression=evaluate(ExactCache(m),'test')
    result=dict(kind=kind,device=torch.cuda.get_device_name(),torch=torch.__version__,shape=[70,80],inference_batch=512,training_batch=train_batch,encoder_ms=enc*1000,reader_ms=inf*1000,map_cache_bytes_per_world=memory_bytes,warmup_seconds=warm,rows=rows,amp_test=regression,scope='Synthetic network-only PPO cost; no simulator, cache detection, buffer or GAE. Refresh intervals are hypothetical cost scenarios, not tested stale-map quality. Fully trainable and frozen encoders are reported separately. Count pooling has no learned encoder parameters.',provenance=provenance(kind))
    result['parameters']=sum(p.numel() for p in m.parameters());result['other_gpu_processes_at_end']=[x for x in subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,process_name','--format=csv,noheader'],text=True).strip().splitlines() if x.split(',')[0].strip()!=str(os.getpid())]
    save_json(ROOT/'results'/f'remembered-grid-compact-{kind}-performance.json',result);print('performance',kind,rows,flush=True)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['remaining','refine_counts','quality','benchmark']);ap.add_argument('--kind',choices=KINDS);args=ap.parse_args();torch.set_num_threads(1);torch.backends.cudnn.benchmark=True
    if args.mode in ('remaining','refine_counts'):
        trained=['counts2','count_edges'] if args.mode=='refine_counts' else ['coarse','counts']
        evaluated=trained if args.mode=='refine_counts' else ['attn','coarse','counts']
        for kind in trained:
            with (OUT/f'compact-{kind}-training.log').open('w') as log:subprocess.run([str(ROOT/'.venv/bin/python'),str(HERE/'run.py'),'--arm','terrain','--architecture',kind,'--updates','12000'],stdout=log,stderr=subprocess.STDOUT,check=True)
        for kind in evaluated:
            quality(kind);benchmark(kind);torch.cuda.empty_cache()
    elif args.mode=='quality':quality(args.kind)
    else:benchmark(args.kind)
if __name__=='__main__':main()
