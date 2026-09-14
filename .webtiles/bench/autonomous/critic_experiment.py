"""Frozen-policy Monte Carlo critic experiment. Never updates/promotes an actor.

Compact frozen actor context + pooled legal-action descriptors avoids persisting
100k floats per observation. This tests critic inputs, not a new spatial encoder.
"""
import os
for key, value in {'DCSS_REPRESENTATION':'spatial-v6','DCSS_HEALTH_FEATURES':'1',
                   'DCSS_REST_ONLY':'1','DCSS_VISIT_MEMORY':'1',
                   'DCSS_EXPLORATION_SCORE':'1','DCSS_TARGET_DETAILS':'1'}.items():
    os.environ[key] = value

import argparse
import concurrent.futures
import copy
import hashlib
import json
import random
import time
from pathlib import Path
import torch
from torch import nn
from model import load_model, tensor_for_actions
from general_env import GeneralEnvironment, ENGINE, HERE, sha
from teacher import _actions
from episode_budget import DecisionBudget
from exploration_score import learning_score, report_fields
from data_split import assert_training_seed, held_out_seed
from bootstrap_repair import write
from train_ppo_pilot import atomic_torch
from ppo_core import sample, SCALE
import storage

VERSION = 'frozen-policy-monte-carlo-critic-v1'


def actor_digest(actor):
    h = hashlib.sha256()
    for name, tensor in sorted(actor.net.state_dict().items()):
        h.update(name.encode()); h.update(tensor.detach().cpu().numpy().tobytes())
    return h.hexdigest()


def pool_actions(actions):
    """Permutation invariant; retains route/visit features missing from state."""
    if not len(actions):
        raise ValueError('nonterminal observation must have legal actions')
    return torch.cat((actions.mean(0), actions.max(0).values))


def remaining_targets(before, final_score, terminal):
    # An administrative cutoff is not a known final return.
    return (torch.tensor([(final_score - x) / SCALE for x in before])
            if terminal else None)


def seed_plan(start, train, validation, test):
    groups = {'train':[start+i for i in range(train)],
              'validation':[(0xC<<60)+start+i for i in range(validation)],
              'test':[(0xD<<60)+start+i for i in range(test)]}
    for seed in groups['train']: assert_training_seed(seed)
    flat = sum(groups.values(), [])
    if len(set(flat)) != len(flat): raise ValueError('overlapping seed splits')
    return groups


def collect(root, actor, split, seed, policy_seed, steps, stride):
    root = Path(root); root.mkdir(parents=True, exist_ok=True)
    if (root/'result.json').exists():
        result = json.loads((root/'result.json').read_text())
        if result.get('error') or (root/'samples.pt').exists(): return result
    if split == 'train': assert_training_seed(seed)
    elif not held_out_seed(seed): raise ValueError('validation/test must be quarantined')
    env = GeneralEnvironment(root/'actor', seed=str(seed),
                             data_role='training' if split == 'train' else 'screen')
    env.record_events = False
    rng = random.Random(policy_seed)
    budget = DecisionBudget(per_floor=2000, total=steps)
    contexts=[]; pools=[]; scores=[]; meta=[]; trace=[]
    started=time.time()
    try:
        state=env.reset()
        if state.get('target_details_version') != 'visible-melee-target-v1':
            raise ValueError('missing corrected target interface')
        # Random phase gives uniform inclusion probability, not danger-biased sampling.
        phase=random.Random(policy_seed+991).randrange(stride)
        while not state.get('terminal') and not budget.reason(state):
            with torch.no_grad():
                base, actions=tensor_for_actions(state, _actions(state))
                context=actor.net.encode_context(base)
                logits=actor.net.head(torch.cat((context.expand(len(actions),-1),actions),1)).squeeze(-1)
                logp=logits.log_softmax(0)
                if not torch.isfinite(logp).all(): raise ValueError('nonfinite policy')
                index=sample(logp,rng)
                if budget.total % stride == phase:
                    contexts.append(context[0].clone()); pools.append(pool_actions(actions))
                    scores.append(learning_score(state))
                    meta.append({'decision':budget.total,'level':state.get('level'),
                                 'native_score':state.get('score')})
            before=learning_score(state)
            kind=_actions(state)[index]['kind']
            after=env.step(index); budget.record(state,after)
            trace.append({'action_index':index,'kind':kind,'before':before,
                          'after':learning_score(after),'level':state.get('level'),
                          'turn':state.get('turn')})
            state=after
        terminal=bool(state.get('terminal'))
        final=learning_score(state)
        targets=remaining_targets(scores,final,terminal)
        if trace and abs(sum(t['after']-t['before'] for t in trace)-(final-trace[0]['before']))>1e-6:
            raise ValueError('score telescope failed')
        atomic_torch(root/'samples.pt', {'version':VERSION,'seed':str(seed),'split':split,
            'context':torch.stack(contexts) if contexts else torch.empty(0,544),
            'navigation':torch.stack(pools) if pools else torch.empty(0,0),
            'targets':targets,'metadata':meta,'scores_before':scores})
        write(root/'trace.json',trace)
        result={'seed':str(seed),'split':split,'policy_seed':policy_seed,
                'terminal':state.get('terminal'),'censored':not terminal,
                'cutoff':budget.reason(state),'steps':budget.total,'samples':len(scores),
                'final_level':state.get('level'),**report_fields(state),
                'native_score':state.get('score'),'elapsed_seconds':time.time()-started}
    except Exception as exc:
        result={'seed':str(seed),'split':split,'error':repr(exc),'steps':budget.total}
    finally:
        env.close(); storage.finish_logs(env.works)
    write(root/'result.json',result)
    return result


class Critic(nn.Module):
    def __init__(self, size):
        super().__init__()
        self.net=nn.Sequential(nn.Linear(size,128),nn.LayerNorm(128),nn.ReLU(),
                               nn.Linear(128,128),nn.ReLU(),nn.Linear(128,1))

    def forward(self,x): return self.net(x).squeeze(-1)


def dataset(root, split, seeds):
    games=[]
    for seed in seeds:
        path=root/'games'/split/str(seed)
        result=json.loads((path/'result.json').read_text())
        if result.get('error') or result.get('censored') or not result.get('samples'): continue
        row=torch.load(path/'samples.pt',weights_only=False)
        if row['targets'] is None: raise ValueError('censored labels entered fit')
        games.append(row)
    return games


def tensors(games, rich):
    xs=[]; ys=[]; ws=[]
    for row in games:
        xs.append(torch.cat((row['context'],row['navigation']),1) if rich else row['context'])
        ys.append(row['targets'])
        ws.append(torch.full((len(row['targets']),),1/len(row['targets'])))
    x=torch.cat(xs); y=torch.cat(ys); w=torch.cat(ws); w/=w.sum()
    return x,y,w


def metrics(pred,y,w):
    mean=(y*w).sum(); variance=((y-mean).square()*w).sum()
    residual=y-pred; mse=(residual.square()*w).sum()
    centered=((residual-(residual*w).sum()).square()*w).sum()
    return {'seed_balanced_mse':float(mse),'seed_balanced_mae':float((residual.abs()*w).sum()),
            'explained_variance':float(1-centered/variance) if variance>0 else None,
            'samples':len(y),'target_mean':float(mean), 'units':'training_score / 1000'}


def fit(root, groups, epochs, update):
    games={split:dataset(root,split,seeds) for split,seeds in groups.items()}
    counts={s:len(g) for s,g in games.items()}
    if min(counts.values())<2:
        return {'valid':False,'reason':'need at least two uncensored games in every split',
                'completed_games':counts}
    output={'valid':True,'completed_games':counts,
            'warning':'Calibration conditional on uncensored games; frozen spatial encoder. Not gameplay improvement.'}
    for rich in (False,True):
        name='navigation' if rich else 'state_only'
        train=tensors(games['train'],rich); val=tensors(games['validation'],rich)
        x,y,w=train
        # Train-only normalization and seed-balanced loss/sampling.
        mean=(x*w[:,None]).sum(0)
        std=(((x-mean).square()*w[:,None]).sum(0)).sqrt().clamp_min(.01)
        x=(x-mean)/std; vx=(val[0]-mean)/std
        torch.manual_seed(771)
        critic=Critic(x.shape[1]); optim=torch.optim.Adam(critic.parameters(),lr=3e-4)
        best=float('inf'); best_state=None; history=[]
        for epoch in range(epochs):
            critic.train()
            for _ in range(max(1,(len(y)+63)//64)):
                ids=torch.multinomial(w,64,replacement=True)
                loss=(critic(x[ids])-y[ids]).square().mean()
                if not torch.isfinite(loss): raise ValueError('nonfinite critic loss')
                optim.zero_grad();loss.backward();nn.utils.clip_grad_norm_(critic.parameters(),1.)
                optim.step()
            critic.eval()
            with torch.no_grad(): vm=metrics(critic(vx),val[1],val[2])
            history.append({'epoch':epoch+1,**vm})
            if vm['seed_balanced_mse']<best:
                best=vm['seed_balanced_mse'];best_state=copy.deepcopy(critic.state_dict());best_epoch=epoch+1
            update(phase='fitting',critic=name,epoch=epoch+1)
        critic.load_state_dict(best_state)
        atomic_torch(root/(name+'.pt'),{'version':VERSION,'rich':rich,'size':x.shape[1],
                     'state_dict':best_state,'mean':mean,'std':std,'epoch':best_epoch})
        result={'selected_epoch':best_epoch,'history':history}
        constant=float((y*w).sum())
        for split in ('validation','test'):
            sx,sy,sw=tensors(games[split],rich)
            with torch.no_grad(): predictions=critic((sx-mean)/std)
            result[split]=metrics(predictions,sy,sw)
            result[split]['constant_baseline']=metrics(torch.full_like(sy,constant),sy,sw)
            atomic_torch(root/f'{name}-{split}-predictions.pt',
                         {'prediction':predictions,'target':sy,'weights':sw,
                          'seed_order':[g['seed'] for g in games[split]]})
        output[name]=result
        write(root/'fit-progress.json',output)
    output['navigation_test_mse_delta']=output['navigation']['test']['seed_balanced_mse']-output['state_only']['test']['seed_balanced_mse']
    return output


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--initial',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--train',type=int,default=32);p.add_argument('--validation',type=int,default=8)
    p.add_argument('--test',type=int,default=8);p.add_argument('--seed-start',type=int,default=62014000)
    p.add_argument('--steps',type=int,default=12000);p.add_argument('--stride',type=int,default=16)
    p.add_argument('--workers',type=int,default=3);p.add_argument('--epochs',type=int,default=30)
    args=p.parse_args()
    if min(args.train,args.validation,args.test,args.steps,args.stride,args.workers,args.epochs)<1:
        p.error('counts must be positive')
    root=args.output.resolve();root.mkdir(parents=True,exist_ok=True)
    storage.configure(root);torch.set_num_threads(1)
    config={k:str(v.resolve()) if isinstance(v,Path) else v for k,v in vars(args).items()}
    config.update(version=VERSION,initial_sha256=sha(args.initial),engine_sha256=sha(ENGINE),
                  code_sha256=sha(Path(__file__)),features_sha256=sha(HERE/'structured_features.py'),
                  bridge_sha256=sha(HERE/'general_bridge.lua'),actor_updates=False,promotion=False)
    if (root/'config.json').exists() and json.loads((root/'config.json').read_text())!=config:
        raise ValueError('config/source differs from saved run; choose new output')
    write(root/'config.json',config)
    if (root/'comparison.json').exists(): return
    groups=seed_plan(args.seed_start,args.train,args.validation,args.test)
    write(root/'seeds.json',groups)
    actor,_=load_model(args.initial);actor.requires_grad_(False);before=actor_digest(actor)
    status={'phase':'collecting','completed':0,'total':sum(map(len,groups.values())),
            'errors':0,'censored':0,'actor_updates':False,'promotion':False}
    def update(**values):
        status.update(values);status['updated_at']=time.time();write(root/'latest_status.json',status)
    update()
    tasks=[(s,n) for s,seeds in groups.items() for n in seeds]
    results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        pending=[pool.submit(collect,root/'games'/s/str(n),actor,s,n,73100+i,args.steps,args.stride)
                 for i,(s,n) in enumerate(tasks)]
        for future in concurrent.futures.as_completed(pending):
            results.append(future.result())
            write(root/'collection.json',results)
            update(completed=len(results),errors=sum('error' in r for r in results),
                   censored=sum(bool(r.get('censored')) for r in results))
    result=fit(root,groups,args.epochs,update)
    result['actor_unchanged']=before==actor_digest(actor)
    result['actor_sha256']=before
    if not result['actor_unchanged']: raise ValueError('frozen actor mutated')
    write(root/'comparison.json',result)
    update(phase='complete',valid=result['valid'],actor_unchanged=True)


if __name__=='__main__': main()
