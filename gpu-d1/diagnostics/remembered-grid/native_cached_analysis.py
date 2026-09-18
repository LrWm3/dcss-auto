"""Report selected-model quality, branch ablation, and compiled replay speed."""
import hashlib,json,time
from pathlib import Path
import torch
from run import evaluate,save_json
from native_cached_exact import make_model,CachedInference
from native_curriculum import factory
from fullsize_navigation import FullEnv,build_full
from native_remedies import make_model as base_model
from symbolic_execution import PolicyExecution,StaticInference
from runtime import ROOT,OUT

def main():
    torch.set_num_threads(1);torch.manual_seed(0);torch.backends.cudnn.benchmark=True;build_full()
    name='native-cached-exact-seed0';folder=OUT/name
    report=json.loads((ROOT/'results'/f'{name}.json').read_text());assert report['finished']
    model=make_model();model.load_state_dict(torch.load(folder/'selected.pt',weights_only=False)['model'])
    policy=CachedInference(model)
    for key,cls in [('middle_erased_test',factory(1)),('full_erased_test',FullEnv)]:
        report[key]=evaluate(policy,'test',limit=1024,env_class=cls,intervene='erase_exact')
        print(key,report[key]['summary'],flush=True)
    env=factory(1)('validation',32);env.reset(seed=71);trajectory=[]
    for _ in range(96):
        trajectory.append((env.grid.clone(),env.mask.clone(),env.stats.clone()));env.step(env.labels.clone(),limit=1024)
    report['replay_benchmark']={}
    candidates=[('coarse_optimized',StaticInference(PolicyExecution(base_model(),True),True,True)),
                ('exact_uncached_compiled',CachedInference(model,False,True)),
                ('exact_cached_compiled',CachedInference(model,True,True))]
    for label,agent in candidates:
        # Full warmup includes all observed partial refresh batch shapes.
        agent.reset_cache()
        for args in trajectory:agent(*args)
        torch.cuda.synchronize();start=time.monotonic()
        for _ in range(2):
            agent.reset_cache()
            for args in trajectory:agent(*args)
        torch.cuda.synchronize();elapsed=time.monotonic()-start
        report['replay_benchmark'][label]=dict(seconds=elapsed,decisions_per_second=6144/elapsed)
        print(label,report['replay_benchmark'][label],flush=True)
    report['experiment']='Cached exact spatial residual plus pretrained coarse branch; exact player XY added separately.'
    report['benchmark_scope']='Policy-only replay at batch 32 on 80x70 maps, same teacher trajectories; not PPO throughput. Coarse uses a CUDA graph; exact uses compiled readout, eager cache/preprocessing.'
    report['implementation_sha256']={n:hashlib.sha256(Path(__file__).with_name(n).read_bytes()).hexdigest() for n in ['native_cached_exact.py','native_cached_screen.py','native_remedies.py']}
    save_json(ROOT/'results'/f'{name}.json',report);save_json(folder/'progress.json',report)

if __name__=='__main__':main()
