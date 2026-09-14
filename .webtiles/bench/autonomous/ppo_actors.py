"""Persistent-game PPO chunks and independent sampled/greedy evaluation."""
import gzip
import json
import math
import random
import time
from collections import Counter
from pathlib import Path

from general_env import GeneralEnvironment
from episode_budget import DecisionBudget
from teacher import _actions
from data_split import assert_training_seed, held_out_seed
from bootstrap_repair import write
from ppo_core import distribution, sample, reward_delta, SCALE
from exploration_score import report_fields, learning_score
from retry_exploration_fit import loop_tick
import storage


def tuples(value):
    return tuple(tuples(v) for v in value) if isinstance(value,list) else value


def collect_chunk(root, model, lane, steps, fresh=False):
    root=Path(root)
    root.mkdir(parents=True,exist_ok=True)
    previous=root/'result.json'
    if previous.exists():
        result=json.loads(previous.read_text())
        with gzip.open(root/'trajectory.json.gz','rt') as f:
            return json.load(f),result
    lane=dict(lane)
    assert_training_seed(lane['seed_base'])
    rng=random.Random()
    rng.setstate(tuples(lane['rng_state']))
    if fresh and lane.get('checkpoint'):
        lane['checkpoint']=None
        lane['episode']+=1
        lane['budget']=None
    rows=[]; episodes=[]; counts=Counter(); melee=Counter(); reward_sum=0.
    env=None; state=None; started=time.time(); loops=0; actions=[]
    try:
        while len(rows)<steps:
            if env is None:
                seed=lane['seed_base']+lane['episode']
                assert_training_seed(seed)
                env=GeneralEnvironment(root/f'episode-{lane["episode"]}',seed=str(seed),data_role='training')
                env.record_events=False
                state=env.reset(lane.get('checkpoint'))
                if state.get('target_details_version')!='visible-melee-target-v1':
                    raise ValueError('missing corrected target interface')
                budget=DecisionBudget()
                b=lane.get('budget')
                if b:
                    budget.floors=Counter(b['decisions_by_floor'])
                    budget.total=b['total_decisions'];budget.no_turn=b['consecutive_no_turn']
                segment_start=learning_score(state)
                segment_reward=0.
            logp,value=distribution(model,state)
            if rows and not rows[-1]['segment_end']:
                rows[-1]['next_value']=value
            idx=sample(logp,rng)
            action=_actions(state)[idx]
            after=env.step(idx)
            budget.record(state,after)
            reward=reward_delta(state,after)
            reward_sum+=reward;segment_reward+=reward
            counts[action['kind']]+=1
            if action['kind']=='MELEE':melee[action.get('target_name','unknown')]+=1
            actions.append(action);actions=actions[-4:]
            loops+=int(loop_tick(after,actions))
            terminal=bool(after.get('terminal'))
            cutoff=budget.reason(after)
            end=terminal or bool(cutoff) or len(rows)+1==steps
            row={'observation':state,'action_index':idx,'log_probs':logp.tolist(),
                 'value':value,'reward':reward,'terminated':terminal,'segment_end':end,
                 'seed':str(lane['seed_base']+lane['episode']),
                 'score_before':learning_score(state),'score_after':learning_score(after),
                 'native_before':state.get('score'),'native_after':after.get('score'),
                 'turn_delta':after.get('turn',0)-state.get('turn',0),
                 'next_value':None}
            rows.append(row);state=after
            if end:
                row['next_value']=0. if terminal else distribution(model,state)[1]
                if not math.isclose(segment_reward*SCALE,learning_score(state)-segment_start,abs_tol=1e-7):
                    raise ValueError('score deltas failed telescoping audit')
                episodes.append({'seed':row['seed'],'terminal':state.get('terminal'),
                                 'cutoff':cutoff or ('rollout_boundary' if not terminal else None),
                                 'level':state.get('level'),**report_fields(state),
                                 'score':state.get('score'),'segment_decisions':sum(r['seed']==row['seed'] for r in rows),
                                 'bootstrap_value':row['next_value']})
                if not terminal and not cutoff:
                    target=root/'continuation'
                    if target.exists():
                        # A crash after snapshot publication but before result
                        # commit must not make the next attempt fail forever.
                        target=root/f'continuation-retry-{time.time_ns()}'
                    env.save_state(target)
                    lane['checkpoint']=str(target.resolve());lane['budget']=budget.summary()
                else:
                    lane['episode']+=1;lane['checkpoint']=None;lane['budget']=None
                env.close();storage.finish_logs(env.works);env=None
        lane['rng_state']=rng.getstate()
        result={'steps':len(rows),'episodes':episodes,'lane':lane,'reward_sum':reward_sum,
                'action_counts':dict(counts),'melee_targets':dict(melee),'loop_ticks':loops,
                'elapsed_seconds':time.time()-started,'telescoping_passed':True}
        storage.guard()
        tmp=root/'trajectory.json.gz.tmp'
        with gzip.open(tmp,'wt') as f:json.dump(rows,f)
        tmp.replace(root/'trajectory.json.gz')
        write(previous,result)
        return rows,result
    except Exception as exc:
        write(root/'failure.json',{'error':repr(exc),'steps':len(rows)})
        # Discard partial on-policy data rather than treating simulator failure as death.
        return [],{'error':repr(exc),'lane':lane,'steps':0}
    finally:
        if env is not None:env.close()


def evaluate_episode(root,model,seed,policy_seed,steps=2000,greedy=False):
    if not held_out_seed(seed):raise ValueError('evaluation requires quarantined seed')
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    if (root/'result.json').exists():return json.loads((root/'result.json').read_text())
    env=GeneralEnvironment(root/'actor',seed=str(seed),data_role='screen')
    env.record_events=False
    rng=random.Random(policy_seed);counts=Counter();melee=Counter();actions=[];loops=0
    budget=DecisionBudget(per_floor=2000,total=steps)
    started=time.time()
    try:
        state=env.reset()
        while not state.get('terminal') and not budget.reason(state):
            logp,_=distribution(model,state)
            idx=int(logp.argmax()) if greedy else sample(logp,rng)
            action=_actions(state)[idx];counts[action['kind']]+=1
            if action['kind']=='MELEE':melee[action.get('target_name','unknown')]+=1
            after=env.step(idx);budget.record(state,after);state=after
            actions.append(action);actions=actions[-4:]
            loops+=int(loop_tick(state,actions))
        snapshot=None
        if not state.get('terminal'):
            snapshot=root/'cutoff-state'
            if snapshot.exists():snapshot=root/f'cutoff-state-retry-{time.time_ns()}'
            env.save_state(snapshot)
        result={'seed':str(seed),'policy_sampling_seed':policy_seed,'greedy':greedy,
                'score':state.get('score'),**report_fields(state),'final_level':state.get('level'),
                'terminal_kind':state.get('terminal'),'steps':budget.total,
                'truncated':not bool(state.get('terminal')),'cutoff_reason':budget.reason(state),
                'action_counts':dict(counts),'melee_targets':dict(melee),'loop_ticks':loops,
                'resume_checkpoint':str(snapshot) if snapshot else None,
                'elapsed_seconds':time.time()-started}
    except Exception as exc:result={'seed':str(seed),'error':repr(exc)}
    finally:
        env.close();storage.finish_logs(env.works)
    write(root/'result.json',result)
    return result
