"""Bounded, resumable PPO pilot; never promotes a champion automatically."""
import os
for key,value in {'DCSS_REPRESENTATION':'spatial-v6','DCSS_HEALTH_FEATURES':'1',
                  'DCSS_REST_ONLY':'1','DCSS_VISIT_MEMORY':'1',
                  'DCSS_EXPLORATION_SCORE':'1','DCSS_TARGET_DETAILS':'1'}.items():
    os.environ[key]=value

import argparse
import concurrent.futures
import json
import random
import time
from pathlib import Path
import torch

from model import load_model,save_model
from general_env import ENGINE,HERE,sha
from bootstrap_repair import write
from try_visit_memory import summary
from ppo_core import VERSION,initialise_critic,fit_ppo
from ppo_actors import collect_chunk,evaluate_episode
import storage


def atomic_torch(path, value):
    storage.guard()
    tmp=path.with_name(path.name+'.tmp')
    torch.save(value,tmp);tmp.replace(path)


def paired(before,after):
    if len(before)!=len(after) or any('error' in r for r in before+after):
        return {'valid':False,'reason':'incomplete paired evaluation'}
    if any(a['seed']!=b['seed'] for a,b in zip(before,after)):
        raise ValueError('unpaired evaluation seeds')
    delta=[b['score']-a['score'] for a,b in zip(before,after)]
    return {'valid':True,'baseline':summary(before),'candidate':summary(after),
            'mean_native_delta':sum(delta)/len(delta),
            'mean_training_score_delta':sum(b['training_score']-a['training_score']
                                           for a,b in zip(before,after))/len(delta),
            'better':sum(d>0 for d in delta),'worse':sum(d<0 for d in delta),
            'tied':sum(d==0 for d in delta),'paired_native_deltas':delta,
            'warning':'development screen, not promotion evidence'}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--initial',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--replicates',type=int,default=2)
    p.add_argument('--cycles',type=int,default=4)
    p.add_argument('--actors',type=int,default=8)
    p.add_argument('--chunk-steps',type=int,default=256)
    p.add_argument('--eval-count',type=int,default=8)
    p.add_argument('--eval-steps',type=int,default=2000)
    p.add_argument('--eval-every',type=int,default=2)
    p.add_argument('--training-seed-start',type=int,default=61005000)
    p.add_argument('--eval-seed-offset',type=int,default=61005000)
    p.add_argument('--smoke',action='store_true')
    args=p.parse_args()
    if args.smoke:
        args.replicates=1;args.cycles=2;args.actors=2;args.chunk_steps=16
        args.eval_count=2;args.eval_steps=32;args.eval_every=1
    if min(args.replicates,args.cycles,args.actors,args.chunk_steps,args.eval_count,args.eval_steps,args.eval_every)<1:
        p.error('counts and budgets must be positive')
    root=args.output.resolve();root.mkdir(parents=True,exist_ok=True)
    storage.configure(root);torch.set_num_threads(1)
    config={k:str(v.resolve()) if isinstance(v,Path) else v for k,v in vars(args).items()}
    config.update(version=VERSION,engine_sha256=sha(ENGINE),initial_sha256=sha(args.initial),
                  bridge_sha256=sha(HERE/'general_bridge.lua'),
                  features_sha256=sha(HERE/'structured_features.py'),
                  core_sha256=sha(HERE/'ppo_core.py'),actors_sha256=sha(HERE/'ppo_actors.py'),
                  automatic_promotion=False,score_scale=1000,gamma=1.,gae_lambda=.95,
                  actor_lr=1e-5,critic_lr=3e-4,epochs=4,
                  target_details='visible-melee-target-v1')
    cfg=root/'config.json'
    if cfg.exists() and json.loads(cfg.read_text())!=config:
        raise ValueError('resume configuration/code differs; use a new output')
    write(cfg,config)
    status={'phase':'starting','promoted':False,'version':VERSION}
    def update(**values):
        status.update(values);status['updated_at']=time.time()
        write(root/'latest_status.json',status)
    update()
    eval_seeds=[(0xC<<60)+args.eval_seed_offset+i for i in range(args.eval_count)]
    write(root/'evaluation-seeds.json',{'role':'development-only','seeds':eval_seeds,
          'policy_sampling_seeds':[89000+i for i in range(args.eval_count)],
          'final_test_namespace':'0xE reserved; not consumed by this pilot'})
    def evaluate(model,directory,greedy=False):
        def run(pair):
            i,seed=pair
            return evaluate_episode(directory/str(i),model,seed,89000+i,args.eval_steps,greedy)
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(4,args.eval_count)) as pool:
            results=list(pool.map(run,enumerate(eval_seeds)))
        write(directory/'results.json',results)
        return results
    try:
        torch.manual_seed(711)
        initial,_=load_model(args.initial)
        initialise_critic(initial)
        if not (root/'initial.pt').exists():
            save_model(root/'initial.pt',initial,{'ppo_version':VERSION,'critic':'state-value-zero-head',
                       'target_details':'visible-melee-target-v1'})
        update(phase='baseline_sampled_evaluation')
        before=evaluate(initial,root/'baseline-sampled')
        update(baseline=summary(before))
        comparisons=[]
        for rep in range(args.replicates):
            torch.manual_seed(711+rep)
            model,_=load_model(root/'initial.pt')
            actor_opt=torch.optim.Adam(model.net.parameters(),lr=1e-5)
            critic_opt=torch.optim.Adam(model.value_net.parameters(),lr=3e-4)
            lanes=[{'seed_base':args.training_seed_start+rep*1000000+i*10000,
                    'episode':0,'checkpoint':None,'budget':None,
                    'rng_state':random.Random(17001+rep*1000+i).getstate()} for i in range(args.actors)]
            for cycle in range(args.cycles):
                work=root/f'replicate-{rep}'/f'cycle-{cycle:03d}'
                work.mkdir(parents=True,exist_ok=True)
                checkpoint=work/'training-state.pt'
                update(phase='collection',replicate=rep,cycle=cycle)
                if checkpoint.exists():
                    saved=torch.load(checkpoint,map_location='cpu',weights_only=False)
                    model.load_state_dict(saved['model'])
                    actor_opt.load_state_dict(saved['actor_optimizer'])
                    critic_opt.load_state_dict(saved['critic_optimizer']);lanes=saved['lanes']
                    report=saved['training']
                else:
                    def run(i):
                        # Rotate one quarter of lanes, continue the other games
                        # with exact engine and sampler state. No evaluation seeds.
                        fresh=cycle>0 and i%4==cycle%4
                        return collect_chunk(work/'actors'/str(i),model,lanes[i],args.chunk_steps,fresh)
                    with concurrent.futures.ThreadPoolExecutor(max_workers=min(4,args.actors)) as pool:
                        collected=list(pool.map(run,range(args.actors)))
                    rows=[]
                    for i,(chunk,result) in enumerate(collected):
                        if 'error' not in result:
                            rows.extend(chunk);lanes[i]=result['lane']
                    write(work/'collection.json',[result for _,result in collected])
                    update(phase='training',transitions=len(rows),actor_errors=sum('error' in r for _,r in collected))
                    report=fit_ppo(model,rows,actor_opt,critic_opt,seed=5000+rep*100+cycle)
                    atomic_torch(checkpoint,{'model':model.state_dict(),
                        'actor_optimizer':actor_opt.state_dict(),'critic_optimizer':critic_opt.state_dict(),
                        'lanes':lanes,'training':report,'cycle':cycle,'replicate':rep,'version':VERSION})
                write(work/'training.json',report)
                save_model(work/'candidate.pt',model,{'ppo_version':VERSION,'cycle':cycle,'replicate':rep,
                           'target_details':'visible-melee-target-v1','deployment_mode':'sampled-softmax'})
                update(training=report,current_candidate=str(work/'candidate.pt'),
                       training_state=str(checkpoint))
                if (cycle+1)%args.eval_every==0 or cycle+1==args.cycles:
                    update(phase='sampled_evaluation')
                    after=evaluate(model,work/'sampled-evaluation')
                    comparison=paired(before,after)
                    write(work/'comparison.json',comparison)
                    comparisons.append({'replicate':rep,'cycle':cycle,**comparison})
                    update(latest_comparison=comparison)
            # Greedy deployment is a separate behavior, not the PPO objective.
            update(phase='final_greedy_evaluation',replicate=rep)
            greedy_before=evaluate(initial,root/'baseline-greedy',True)
            greedy_after=evaluate(model,root/f'replicate-{rep}'/'final-greedy',True)
            write(root/f'replicate-{rep}'/'greedy-comparison.json',paired(greedy_before,greedy_after))
        write(root/'comparisons.json',comparisons)
        update(phase='complete',comparisons=comparisons,
               warning='bounded pilot; learning progress is empirical, not guaranteed; no promotion')
    except BaseException as exc:
        update(phase='failed',error=repr(exc))
        raise


if __name__=='__main__':main()
