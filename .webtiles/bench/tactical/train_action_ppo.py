"""Fixed-budget masked PPO pilot. Validation after fitting; test never loaded."""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import multiprocessing
import os
from pathlib import Path
import time

os.environ.setdefault('OMP_NUM_THREADS','1')
os.environ.setdefault('MKL_NUM_THREADS','1')

import numpy as np
import torch
from sb3_contrib import MaskablePPO
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.vec_env import SubprocVecEnv

import bench
from action_env import ActionEnv, fixed_action
from goal_controllers import Controller, Recovery

class Progress(BaseCallback):
    def __init__(self, output):
        super().__init__();self.output=Path(output);self.started=time.monotonic()
    def _on_step(self):return True
    def _on_rollout_end(self):
        counts=Counter()
        for path in (self.output/'train').glob('env-*/episodes.jsonl'):
            for line in path.read_text().splitlines():counts[json.loads(line)['outcome']]+=1
        progress=dict(steps=self.num_timesteps,seconds=time.monotonic()-self.started,
                      episode_outcomes=dict(counts))
        (self.output/'progress.json').write_text(json.dumps(progress,indent=2)+'\n')
        print(json.dumps(progress),flush=True)

def evaluate(task):
    config,root,policy,index,model_path=task
    torch.set_num_threads(1)
    root=Path(root)/policy/f'case-{index:02d}'
    env=ActionEnv(config,root,'validation')
    result=dict(policy=policy,case_index=index,outcome='harness_error')
    try:
        obs,_=env.reset(seed=9000+index,options={'case_index':index})
        if policy=='historical_pursue':
            # This baseline retains the old controller's extra tools and macro
            # actions. Report separately from action-matched comparisons.
            controller=Controller('pursue',False); recovery=Recovery()
            state=env.state
            outcome='budget_truncated'
            for step in range(env.max_steps):
                after=env.transport.step(controller(state))
                if after.get('terminal')=='death':outcome='death';state=after;break
                if recovery.observe(state,after):outcome='recovered_quiet';state=after;break
                state=after
            env.state=state
            env.transport.close()
            env.audit.close();env.requests.close();env.finished=True
            if outcome=='death' and bench.sha(Path(state['evidence']))!=state['evidence_sha256']:
                raise RuntimeError('Invalid death evidence')
            result.update(outcome=outcome,steps=step+1,case_id=env.entry['id'],
                          seed=env.entry['seed'],worker=str(env.transport.work))
        else:
            model=MaskablePPO.load(model_path,device='cpu') if policy=='ppo' else None
            rng=np.random.default_rng(9000+index)
            for _ in range(env.max_steps):
                mask=env.action_masks()
                if model is not None:
                    a,_=model.predict(obs,deterministic=True,action_masks=mask)
                elif policy=='random':a=rng.choice(np.flatnonzero(mask))
                else:a=fixed_action(env.state,mask,policy)
                obs,_,terminated,truncated,info=env.step(a)
                if terminated or truncated:break
            result.update(json.loads((env.transport.work/'episode.json').read_text()))
    except Exception as exc:
        result['error']=repr(exc)
    finally:
        env.close()
        root.mkdir(parents=True,exist_ok=True)
        (root/'evaluation.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--steps',type=int,default=6144)
    args=p.parse_args();root=args.output.resolve();root.mkdir(parents=True,exist_ok=False)
    config=json.loads(args.config.read_text())
    if not config.get('preflight_passed') or config.get('test_used'):
        raise ValueError('Missing preflight / test leakage')
    if bench.sha(args.config.parent/'preflight.json')!=config['preflight_sha256']:
        raise ValueError('Preflight changed')
    torch.set_num_threads(1)
    sources=['action_env.py','cached_env.py','fast_env.py','prepare_action_pilot.py',
             'train_action_ppo.py','rich_features.py','goal_controllers.py','audit_action_episodes.py']
    (root/'sources').mkdir()
    for name in sources:(root/'sources'/name).write_bytes((bench.HERE/name).read_bytes())
    manifest=dict(config=str(args.config.resolve()),config_sha256=bench.sha(args.config),
        sources={n:bench.sha(bench.HERE/n) for n in sources},training_steps=args.steps,
        training_seed=42,workers=6,algorithm='MaskablePPO',gamma=.995,n_steps=128,
        batch_size=128,n_epochs=4,learning_rate=.0003,entropy_coefficient=.01,
        policy_layers=[128,128],production_export=False,test_used=False,
        torch=torch.__version__,sb3_contrib=__import__('sb3_contrib').__version__)
    (root/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    env=SubprocVecEnv([lambda i=i:ActionEnv(str(args.config.resolve()),root/'train'/f'env-{i}')
                      for i in range(6)],start_method='spawn')
    started=time.monotonic()
    try:
        model=MaskablePPO('MlpPolicy',env,seed=42,device='cpu',verbose=1,
            n_steps=128,batch_size=128,n_epochs=4,gamma=.995,ent_coef=.01,
            policy_kwargs=dict(net_arch=dict(pi=[128,128],vf=[128,128])))
        model.learn(total_timesteps=args.steps,callback=Progress(root))
        model.save(root/'model')
        (root/'training.json').write_text(json.dumps(dict(completed=True,steps=model.num_timesteps,
            seconds=time.monotonic()-started,model_sha256=bench.sha(root/'model.zip')),indent=2)+'\n')
    except BaseException:
        # SB3 close() can block receiving from other workers after one crashes.
        # Terminate only this pool's owned children and preserve all evidence.
        for process in env.processes:
            if process.is_alive():process.terminate()
        for process in env.processes:process.join(timeout=5)
        env.closed=True
        raise
    finally:
        if not env.closed:env.close()
    policies=['random','pursue','pursue_berserk','historical_pursue','ppo']
    count=sum(e['split']=='validation' for e in config['cases'])
    tasks=[(str(args.config.resolve()),str(root/'validation'),policy,i,str(root/'model.zip'))
           for policy in policies for i in range(count)]
    results=[]
    with ProcessPoolExecutor(max_workers=6,mp_context=multiprocessing.get_context('spawn')) as pool:
        for future in as_completed([pool.submit(evaluate,t) for t in tasks]):
            result=future.result();results.append(result)
            (root/'validation.json').write_text(json.dumps(results,indent=2)+'\n')
            print(json.dumps({k:result.get(k) for k in ['policy','case_index','outcome','steps','error']}),flush=True)
    summary={policy:dict(Counter(r['outcome'] for r in results if r['policy']==policy)) for policy in policies}
    (root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary),flush=True)

if __name__=='__main__':main()
