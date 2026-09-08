"""Small linear Q-learning trainer for verified mined checkpoints.

Uses private engine resets, not offline imitation of losing baseline actions.
Keeps legacy experiment.py/model exports unchanged. Models here are not exports
for the production RC. Evaluation never updates the learner.
"""
import argparse
from collections import Counter
import copy
import json
from pathlib import Path
import random
import time

from bench import Environment, ENGINE, ROOT, HERE, sha
from experiment import DIRECTIONS
from mine_encounters import encounter_recovered

VERSION = 2


def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True)+'\n')


def enemies(state):
    return list(state.get('monsters', {}).values())


def actions(state):
    """Conservative visible-geometry mask, not a proof of engine legality."""
    out=['baseline','wait']
    if state.get('confused'): return out
    adjacent=[e for e in enemies(state) if max(abs(e['x']),abs(e['y']))<=1 and e.get('reachable')]
    if adjacent:
        out.append('melee')
        if not state.get('berserk') and not state.get('cooldown'): out.append('berserk')
    if any(s in state.get('status','').lower() for s in ('held','constricted','mesmer','rooted','petrif')):
        return out
    for action,(x,y) in DIRECTIONS.items():
        cell=state.get('cells',{}).get(f'{x}:{y}',{})
        if (not cell.get('traversable') or cell.get('cloud') or cell.get('invisible_monster')
                or any(e['x']==x and e['y']==y for e in enemies(state))): continue
        if cell.get('feature') in ('floor','open_door') or cell.get('feature','').startswith('stone_stairs_'):
            out.append(action)
    return out


def features(state, memory):
    es=enemies(state);hp=max(0,min(1,state['hp']/state['max_hp']))
    nearest=min(es,key=lambda e:max(abs(e['x']),abs(e['y'])),default=None)
    f=dict(bias=1.,hp=hp,critical=float(hp<.3),wounded=float(hp<.6),
           enemies=min(8,len(es))/8,red=min(4,sum(e['threat']>=3 for e in es))/4,
           yellow=min(6,sum(e['threat']==2 for e in es))/6,
           adjacent=min(8,sum(max(abs(e['x']),abs(e['y']))<=1 for e in es))/8,
           distance=max(abs(nearest['x']),abs(nearest['y']))/8 if nearest else 1.,
           nearest_x=nearest['x']/8 if nearest else 0.,nearest_y=nearest['y']/8 if nearest else 0.,
           recent_hp_loss=max(0,memory['last_hp']-hp),
           peak_threat=memory['peak_threat']/3,age=min(200,memory['decisions'])/200,
           noops=min(8,memory['noops'])/8,unseen=float(not es and not state.get('safe')))
    for flag in ('berserk','cooldown','confused','poisoned','on_fire','safe'):
        f[flag]=float(bool(state.get(flag)))
    for a,(x,y) in DIRECTIONS.items():
        cell=state.get('cells',{}).get(f'{x}:{y}',{})
        f['open_'+a]=float(a in actions(state))
        f['cloud_'+a]=float(bool(cell.get('cloud')))
        f['enemy_'+a]=float(any(e['x']==x and e['y']==y for e in es))
    return f


def value(model, action, f):
    return sum(model.get(action,{}).get(k,0)*v for k,v in f.items())


def choose(model, state, memory, rng, epsilon=0):
    allowed=actions(state);f=features(state,memory)
    if epsilon and rng.random()<epsilon: return rng.choice(allowed)
    # Stable baseline-first ties make an untrained policy a genuine RC control.
    return max(allowed,key=lambda a:value(model,a,f))


def update(model, action, f, reward, bootstrap, discount, alpha):
    weights=model.setdefault(action,{})
    error=reward+discount*bootstrap-value(model,action,f)
    # Normalized step keeps broad feature vectors from exploding the update.
    rate=alpha/max(1.,sum(v*v for v in f.values()))
    for k,v in f.items(): weights[k]=weights.get(k,0)+rate*error*v


def outcome(after, initial_floor, decisions, elapsed, noops, cfg):
    if after.get('terminal')=='death': return 'death'
    if after['floor']!=initial_floor: return 'floor_change'
    if encounter_recovered(after): return 'safe_recovery'
    if noops>=cfg.get('max_noops',8): return 'no_turn_stall'
    if decisions>=cfg['steps'] or elapsed>=cfg['turns']: return 'budget_truncated'
    return None


def reward_for(label, turns):
    # Equal terminal reward irrespective of time spent: do not prefer early death.
    # Budgets remain unfinished, and healing/waiting cannot farm positive reward.
    return 100 if label=='safe_recovery' else -100 if label=='death' else 0


def run_episode(entry, root, policy, model, rng, cfg, training=False, epsilon=0, controller=None, samples=None):
    env=Environment(root);start=time.monotonic()
    result=dict(case_id=entry['id'],seed=entry['seed'],policy=policy,training=training,
                outcome='harness_error',decisions=0,total_reward=0.,actions={})
    counts=Counter()
    try:
        state=env.reset(Path(entry['case']))
        if state.get('terminal'): raise RuntimeError('Terminal checkpoint')
        first_turn=state['turn'];floor=state['floor']
        memory=dict(last_hp=state['hp']/state['max_hp'],peak_threat=0,decisions=0,noops=0)
        result.update(initial_turn=first_turn,initial_hp=state['hp'],initial_max_hp=state['max_hp'],
                      reset_seconds=round(time.monotonic()-start,3))
        for decision in range(1,cfg['steps']+1):
            memory['peak_threat']=max(memory['peak_threat'],max((e['threat'] for e in enemies(state)),default=0))
            f=features(state,memory)
            if controller is not None:
                action=controller(state)
                if action not in actions(state):raise ValueError('Tactic chose masked action: '+action)
            elif policy=='baseline': action='baseline'
            elif policy=='melee': action='melee' if 'melee' in actions(state) else 'baseline'
            else: action=choose(model,state,memory,rng,epsilon if training else 0)
            if samples is not None:
                samples.append(dict(features=dict(f),allowed=actions(state),action=action))
            after=env.step(action);counts[action]+=1
            delta=max(0,after.get('turn',state['turn'])-state['turn'])
            nxt=dict(last_hp=state['hp']/state['max_hp'],
                     peak_threat=max(memory['peak_threat'],max((e['threat'] for e in enemies(after)),default=0)),
                     decisions=decision,noops=memory['noops']+1 if delta==0 else 0)
            label=outcome(after,floor,decision,after.get('turn',state['turn'])-first_turn,nxt['noops'],cfg)
            reward=reward_for(label,delta)
            # Bootstrap time limits; absorbing endpoints/stalls do not bootstrap.
            bootstrap=0.
            if label in (None,'budget_truncated'):
                nf=features(after,nxt)
                bootstrap=max(value(model,a,nf) for a in actions(after))
            if training: update(model,action,f,reward,bootstrap,cfg['gamma']**max(1,delta),cfg['alpha'])
            with (env.work/'rewards.jsonl').open('a') as stream:
                stream.write(json.dumps(dict(decision=decision,action=action,reward=reward,
                    outcome=label,terminated=label in ('death','safe_recovery'),
                    truncated=bool(label and label not in ('death','safe_recovery')),
                    bootstrap=bootstrap,turn_delta=delta))+'\n')
            result.update(decisions=decision,total_reward=result['total_reward']+reward,
                          final_turn=after.get('turn',state['turn']),final_hp=after.get('hp',0),
                          final_max_hp=after.get('max_hp',state['max_hp']))
            state=after;memory=nxt
            if label:
                result['outcome']=label;break
        # A proxy recovery need not be durable. Audit the RC handoff separately;
        # do not turn its later actions into learner rewards or mutate eval weights.
        if result['outcome']=='safe_recovery' and not training and cfg.get('handoff_steps',0):
            handoff=dict(outcome='budget_alive',decisions=0)
            handoff_noops=0
            try:
                for i in range(cfg['handoff_steps']):
                    previous_turn=state['turn']
                    state=env.step('baseline');handoff['decisions']=i+1
                    if state.get('terminal'):
                        handoff['outcome']='death';break
                    handoff_noops=handoff_noops+1 if state['turn']==previous_turn else 0
                    if handoff_noops>=cfg.get('max_noops',8):
                        handoff['outcome']='no_turn_stall';break
                    if state['floor']!=floor:
                        handoff['outcome']='floor_change';break
                handoff.update(final_hp=state.get('hp'),final_floor=state.get('floor'),
                               recovered_at_end=not state.get('terminal') and encounter_recovered(state))
            except Exception as exc:
                handoff.update(outcome='harness_error',error=str(exc))
            result['handoff']=handoff
    except Exception as exc:
        result['error']=str(exc)
    finally:
        work=Path(getattr(env,'work',root))
        result.update(worker=str(work),elapsed_seconds=round(time.monotonic()-start,3),actions=dict(counts))
        for name in ('transitions.jsonl','rewards.jsonl'):
            if (work/name).exists():result[name+'_sha256']=sha(work/name)
        env.close();write(work/'episode.json',result)
    return result


def load_cases(cfg):
    index_path=(ROOT/cfg['dataset']).resolve()
    index=json.loads(index_path.read_text());all_cases={e['id']:e for e in index['cases']}
    if cfg.get('dataset_sha256') and sha(index_path)!=cfg['dataset_sha256']:
        raise ValueError('Dataset index mismatch')
    groups=[]
    for field in ('train_cases','eval_cases'):
        ids=cfg[field]
        if not ids or len(ids)!=len(set(ids)): raise ValueError('Nonempty unique case IDs required')
        group=[]
        for id_ in ids:
            e=all_cases[id_]
            if not e['eligible']:raise ValueError('Unverified case: '+id_)
            case=Path(e['case']);meta=json.loads((case/'case.json').read_text())
            if not meta.get('training_ready'):raise ValueError('Checkpoint not verified')
            for name,field_hash in (('checkpoint.cs','save_sha256'),('trial.rc','rc_sha256')):
                if sha(case/name)!=e[field_hash] or meta[field_hash]!=e[field_hash]:
                    raise ValueError('Checkpoint hash mismatch')
            if e['engine_sha256']!=sha(ENGINE) or meta['engine_sha256']!=sha(ENGINE):
                raise ValueError('Engine mismatch')
            if e['seed']!=meta['seed'] or e['split_group']!=e['seed']:raise ValueError('Seed metadata mismatch')
            group.append(e)
        groups.append(group)
    if cfg.get('evaluation_mode') not in ('in_sample','held_out'):
        raise ValueError('Explicit evaluation_mode required')
    overlap={e['seed'] for e in groups[0]} & {e['seed'] for e in groups[1]}
    if overlap and cfg['evaluation_mode']!='in_sample':raise ValueError('Train/eval seed leakage')
    return groups,index_path


def validate(cfg):
    for name in ('episodes','steps','turns','eval_repeats'):
        if type(cfg.get(name)) is not int or cfg[name]<1:raise ValueError('Positive integer: '+name)
    for name in ('alpha','gamma','epsilon'):
        if not isinstance(cfg.get(name),(int,float)) or not 0<cfg[name]<=1:raise ValueError('Bad '+name)
    for name,default,minimum in (('max_noops',8,1),('handoff_steps',0,0)):
        if type(cfg.get(name,default)) is not int or cfg.get(name,default)<minimum:
            raise ValueError('Bad '+name)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('config',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();cfg=json.loads(a.config.read_text());validate(cfg)
    (train,evaluation),index_path=load_cases(cfg)
    root=a.output.resolve();root.mkdir(parents=True,exist_ok=False)
    write(root/'config.json',cfg)
    write(root/'manifest.json',dict(schema_version=VERSION,engine_sha256=sha(ENGINE),
        dataset_sha256=sha(index_path),trainer_sha256=sha(Path(__file__)),
        recovery_sha256=sha(HERE/'mine_encounters.py'),adapter_sha256=sha(HERE/'bench.py'),
        train=train,evaluation=evaluation,evaluation_mode=cfg['evaluation_mode']))
    model={};rng=random.Random(cfg.get('random_seed',0));results=[]
    schedule=[('before',e,p,False) for e in evaluation for p in ('baseline','melee')
              for _ in range(cfg['eval_repeats'])]
    # Balanced deterministic case cycling; exploration randomness is separately seeded.
    schedule += [('train',train[i%len(train)],'q',True) for i in range(cfg['episodes'])]
    schedule += [('after',e,'q',False) for e in evaluation for _ in range(cfg['eval_repeats'])]
    for i,(phase,entry,policy,training) in enumerate(schedule):
        work=root/f'episode-{i:04d}';work.mkdir()
        before=copy.deepcopy(model)
        result=run_episode(entry,work,policy,model,rng,cfg,training,cfg['epsilon'])
        if not training and before!=model:raise AssertionError('Evaluation mutated model')
        result.update(phase=phase,evaluation_mode=cfg['evaluation_mode'])
        results.append(result);write(root/'results.json',results)
        write(root/'model.json',dict(schema_version=VERSION,kind='linear_q',weights=model,
                                    production_export=False))
        print(json.dumps(result),flush=True)
        if result['outcome']=='harness_error' or result.get('handoff',{}).get('outcome')=='harness_error':break
    summary=dict(evaluation_mode=cfg['evaluation_mode'],episodes=len(results),
        completed=len(results)==len(schedule),model_sha256=sha(root/'model.json'),
        groups=[dict(phase=phase,policy=policy,count=len(rows),
                     outcomes=dict(Counter(r['outcome'] for r in rows)),
                     handoffs=dict(Counter(r['handoff']['outcome'] for r in rows if 'handoff' in r)))
                for phase,policy in sorted({(r['phase'],r['policy']) for r in results})
                for rows in [[r for r in results if (r['phase'],r['policy'])==(phase,policy)]]])
    write(root/'summary.json',summary);print(json.dumps(summary),flush=True)
    return 0 if summary['completed'] and all(r['outcome']!='harness_error' and
        r.get('handoff',{}).get('outcome')!='harness_error' for r in results) else 1


if __name__=='__main__':raise SystemExit(main())
