"""Full-map actor/critic compute benchmark; not an end-to-end simulator/PPO run.

PPO loss uses frozen old log probabilities, clipped advantages, a value loss,
entropy, gradient clipping, Adam and (for AMP) dynamic loss scaling. Four-pass
rates amortize one rollout forward plus four training presentations per decision.
Inputs are synthetic. No learning-quality claims follow from this benchmark.
"""
import argparse,json,time,hashlib,subprocess,os
import torch
from torch import nn
from torch.nn import functional as F
from runtime import SpatialPolicy,PackedPolicy,Packed2Policy,CroppedSpatialPolicy,ThinSpatialPolicy,OUT,ROOT

class FullSpatial(SpatialPolicy):
    """Original layers extended to rectangles for a like-sized cost baseline."""
    def __init__(self,amp=False):
        super().__init__('terrain');self.amp=amp
    def forward(self,grid,mask,stats,intervene=None):
        with torch.autocast('cuda',dtype=torch.float16,enabled=self.amp):
            h,w=grid.shape[-2:];pos=stats[:,2:4];g=grid.float()/255.
            if self.amp:g=g.contiguous(memory_format=torch.channels_last)
            g=torch.cat([g[:,:6],g[:,6:]*g[:,3:4]],1)
            scale=stats.new_tensor([w-1,h-1]);size=stats.new_tensor([w,h])
            lo=self.local(F.grid_sample(g,(self.crop_xy+pos[:,None,None,:])/scale*2-1,mode='nearest',align_corners=True))
            yy,xx=torch.meshgrid(torch.arange(h,device=g.device),torch.arange(w,device=g.device),indexing='ij');xy=torch.stack([xx,yy]).float()[None]
            fine=self.fine(torch.cat([g,(xy-pos[:,:,None,None])/size[None,:,None,None]],1));middle=self.middle(F.max_pool2d(fine,2));coarse=self.coarse(F.max_pool2d(middle,2));context=self.context(coarse)
            middle=self.up_middle(torch.cat([middle,F.interpolate(context,size=middle.shape[-2:],mode='nearest')],1));fine=self.up_fine(torch.cat([fine,F.interpolate(middle,size=fine.shape[-2:],mode='nearest')],1))
            gl=self.readout(F.grid_sample(fine,(self.read_xy+pos[:,None,None,:])/scale*2-1,mode='nearest',align_corners=True).flatten(1))
            return self.head(torch.cat([lo,gl,stats[:,:2]],1)).float().masked_fill(mask==0,-1e9)

class ActorCritic(nn.Module):
    def __init__(self,policy):
        super().__init__();self.policy=policy
        # Additional value output shares the entire representation, as PPO would.
        last=policy.head[-1];new=nn.Linear(last.in_features,20)
        with torch.no_grad():new.weight[:19].copy_(last.weight);new.bias[:19].copy_(last.bias)
        policy.head[-1]=new
    def forward(self,g,mask,s):
        output=self.policy(g,torch.cat([mask,torch.ones_like(mask[:,:1])],1),s)
        return output[:,:19],output[:,19]

def measure(name,iterations=30,train_batch=256,profile=False):
    amp=name!='original_fp32';p=FullSpatial(amp) if name.startswith('original') else ThinSpatialPolicy('terrain',amp) if name.startswith('thin') else CroppedSpatialPolicy('terrain',amp) if name.startswith('cropped') else (Packed2Policy if name=='packed2_amp' else PackedPolicy)('terrain',amp)
    model=ActorCritic(p).cuda()
    if amp:model.to(memory_format=torch.channels_last)
    if 'compile' in name:
        if hasattr(model.policy,'fast_pool'):model.policy.fast_pool=True
        torch._inductor.config.compile_threads=2
        model.compile(fullgraph=True)
    opt=torch.optim.Adam(model.parameters(),lr=1e-5);scaler=torch.amp.GradScaler('cuda',enabled=amp)
    def inputs(n):
        g=torch.randint(0,256,(n,11,70,80),device='cuda',dtype=torch.uint8);mask=torch.ones(n,19,device='cuda');s=torch.tensor([1.,.1,40.,35.],device='cuda').repeat(n,1)
        return g,mask,s
    warmup_seconds=[]
    def timed(fn):
        torch.cuda.synchronize();warmstart=time.perf_counter()
        for _ in range(10):fn()
        torch.cuda.synchronize();warmup_seconds.append(time.perf_counter()-warmstart)
        torch.cuda.synchronize();torch.cuda.reset_peak_memory_stats();start=time.perf_counter()
        for _ in range(iterations):fn()
        torch.cuda.synchronize();return (time.perf_counter()-start)/iterations
    g,mask,s=inputs(512)
    @torch.no_grad()
    def infer():
        logits,v=model(g,mask,s);return torch.distributions.Categorical(logits=logits).sample(),v
    inference=timed(infer);del g,mask,s
    g,mask,s=inputs(train_batch)
    with torch.no_grad():
        logits,oldv=model(g,mask,s);d=torch.distributions.Categorical(logits=logits);actions=d.sample();oldlp=d.log_prob(actions);returns=oldv+torch.randn_like(oldv);advantages=torch.randn_like(oldv)
    def train():
        opt.zero_grad(set_to_none=True);logits,v=model(g,mask,s);d=torch.distributions.Categorical(logits=logits);ratio=(d.log_prob(actions)-oldlp).exp()
        loss=-torch.minimum(ratio*advantages,ratio.clamp(.8,1.2)*advantages).mean()+.25*(v-returns).square().mean()-.01*d.entropy().mean()
        scaler.scale(loss).backward();scaler.unscale_(opt);torch.nn.utils.clip_grad_norm_(model.parameters(),.5);scaler.step(opt);scaler.update()
        return loss
    torch.cuda.reset_peak_memory_stats();training=timed(train);peak=torch.cuda.max_memory_allocated()
    if profile:
        with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU,torch.profiler.ProfilerActivity.CUDA],record_shapes=True) as prof:
            for _ in range(5):train()
            torch.cuda.synchronize()
        (OUT/(name+'-profile.txt')).write_text(prof.key_averages(group_by_input_shape=True).table(sort_by='self_cuda_time_total',row_limit=25))
    assert all(torch.isfinite(p).all() for p in model.parameters())
    result=dict(warmup_seconds=warmup_seconds,name=name,inference_batch=512,training_batch=train_batch,inference_ms=inference*1000,training_ms=training*1000,inference_per_second=512/inference,training_examples_per_second=train_batch/training,network_only_four_epoch_decisions_per_second=1/(inference/512+4*training/train_batch),peak_allocated_bytes=peak,final_loss=float(train()),amp_scale=scaler.get_scale())
    print(json.dumps(result),flush=True);return result

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--iterations',type=int,default=30);ap.add_argument('--allow-contention',action='store_true');ap.add_argument('--names',default='original_fp32,original_amp,cropped_amp');ap.add_argument('--train-batch',type=int,default=256);ap.add_argument('--profile',action='store_true');ap.add_argument('--output',default='remembered-grid-performance.json');args=ap.parse_args()
    processes=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,process_name','--format=csv,noheader'],text=True).strip().splitlines()
    other=[line for line in processes if line.split(',')[0].strip()!=str(os.getpid())]
    if other and not args.allow_contention:raise RuntimeError('GPU occupied; refusing misleading benchmark: '+str(other))
    torch.set_num_threads(1);torch.manual_seed(991);torch.backends.cudnn.benchmark=True
    source_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [__import__('pathlib').Path(__file__),__import__('pathlib').Path(__file__).with_name('runtime.py')]}
    rows=[]
    for name in args.names.split(','):
        rows.append(measure(name,args.iterations,args.train_batch,args.profile));torch.cuda.empty_cache()
    end_processes=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,process_name','--format=csv,noheader'],text=True).strip().splitlines()
    end_other=[line for line in end_processes if line.split(',')[0].strip()!=str(os.getpid())]
    result=dict(source_hashes=source_hashes,other_gpu_processes_at_end=end_other,other_gpu_processes_at_start=other,device=torch.cuda.get_device_name(),torch=torch.__version__,map_shape=[70,80],iterations=args.iterations,rows=rows,scope='Synthetic network-only PPO cost; excludes simulator, observation export, rollout storage, GAE and replay anchoring. Includes Adam, clipping and AMP scaling.',source_sha256=hashlib.sha256(__import__('pathlib').Path(__file__).read_bytes()).hexdigest())
    (ROOT/'results'/args.output).write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
