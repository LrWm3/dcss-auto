"""Small tabular Q-learning smoke test, not a general Crawl agent.

Train and evaluate on one case to test the infrastructure. This is explicitly
in-sample; identical resets are reproducibility tests, not independent seeds.
"""
import argparse
import json
import random
import time
from pathlib import Path

from bench import Environment, HERE, ENGINE, sha

DIRECTIONS = {'n':(0,-1),'s':(0,1),'w':(-1,0),'e':(1,0),
              'nw':(-1,-1),'ne':(1,-1),'sw':(-1,1),'se':(1,1)}


def monsters(state):
    return list(state.get('monsters',{}).values())


def retreat(state):
    enemies=monsters(state)
    choices=[]
    for action,(x,y) in DIRECTIONS.items():
        cell=state.get('cells',{}).get(f'{x}:{y}',{})
        if not cell.get('traversable') or cell.get('cloud') or cell.get('invisible_monster'):
            continue
        if cell.get('feature') not in ('floor','open_door','stone_stairs_up_i',
                                     'stone_stairs_up_ii','stone_stairs_up_iii'):
            continue
        if any(e['x']==x and e['y']==y for e in enemies): continue
        distance=min((max(abs(x-e['x']),abs(y-e['y'])) for e in enemies),default=0)
        choices.append((distance,action))
    return max(choices)[1] if choices else 'wait'


def key(state):
    enemies=monsters(state)
    distance=min((max(abs(e['x']),abs(e['y'])) for e in enemies),default=9)
    return str((min(4,int(5*state['hp']/state['max_hp'])), min(3,len(enemies)),
                min(3,distance),state['berserk'],state['cooldown'],bool(state['status'])))


def options(state):
    out=['wait']
    if monsters(state):
        out += ['tab','retreat']
        if not state['berserk'] and not state['cooldown'] and not state['confused']:
            out += ['berserk']
    return out


def recovered(state):
    # Observable safety proxy, not a claim that unseen enemies are dead.
    return (not state.get('terminal') and not monsters(state) and state['safe']
            and state['hp']>=state['max_hp'] and not state['status']
            and not state['poisoned'] and not state['on_fire'])


def episode(case, workspace, policy, q, rng, budget=200, training=False, fresh=False):
    env=Environment(workspace)
    started=time.monotonic()
    result={'policy':policy,'training':training,'fresh':fresh,'case':str(case),
            'engine_sha256':sha(ENGINE),'outcome':'budget_truncated'}
    safe_since=None
    noops=0
    try:
        state=env.launch() if fresh else env.reset(case)
        result['initial_turn']=state['turn']
        result['reset_seconds']=round(time.monotonic()-started,3)
        for step in range(budget):
            k=key(state); choices=options(state)
            values=q.setdefault(k,{})
            if policy=='baseline': selected='baseline'
            elif policy=='tab': selected='tab' if monsters(state) else 'wait'
            elif policy=='charge':
                adjacent=any(max(abs(e['x']),abs(e['y']))<=1 for e in monsters(state))
                selected='berserk' if adjacent and 'berserk' in choices else ('tab' if monsters(state) else 'wait')
            else:
                selected=(rng.choice(choices) if training and rng.random()<0.35
                          else max(choices,key=lambda a:values.get(a,0)))
            action=retreat(state) if selected=='retreat' else selected
            after=env.step(action)
            noops=noops+1 if after.get('turn')==state['turn'] else 0
            terminal=after.get('terminal')=='death'
            reward=-100 if terminal else -0.1+2*(after['hp']/after['max_hp']-state['hp']/state['max_hp'])
            if noops: reward-=2
            if recovered(after):
                if safe_since is None: safe_since=after['turn']
                if after['turn']-safe_since>=10:
                    result['outcome']='safe_recovery';terminal=True;reward+=100
            else: safe_since=None
            if after.get('terminal')=='death':result['outcome']='death'
            if noops>=8: result['outcome']='no_turn_stall';terminal=True
            if training:
                bootstrap=0 if terminal else max(q.get(key(after),{}).get(a,0) for a in options(after))
                old=values.get(selected,0)
                values[selected]=old+0.3*(reward+0.98*bootstrap-old)
            with (env.work/'rewards.jsonl').open('a') as f:
                f.write(json.dumps({'step':step,'option':selected,'action':action,
                    'reward':reward,'terminal':terminal})+'\n')
            result.update(decisions=step+1,final_turn=after.get('turn',state['turn']),
                          final_hp=after.get('hp',0))
            state=after
            if terminal:break
    except Exception as exc:
        result.update(outcome='harness_error',error=str(exc))
    finally:
        result.update(worker=str(env.work),elapsed_seconds=round(time.monotonic()-started,3))
        (env.work/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        env.close()
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument('case',type=Path)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--episodes',type=int,default=12)
    p.add_argument('--steps',type=int,default=200)
    args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    rng=random.Random(0); q={}; results=[]
    for policy,training in ([('baseline',False),('baseline',False),('tab',False),('charge',False)]
                            +[('q',True)]*args.episodes+[('q',False)]*2):
        result=episode(args.case.resolve(),args.output,policy,q,rng,args.steps,training)
        results.append(result)
        print(json.dumps(result),flush=True)
        (args.output/'results.json').write_text(json.dumps(results,indent=2)+'\n')
        (args.output/'q.json').write_text(json.dumps(q,indent=2)+'\n')
        if result['outcome']=='harness_error':break


if __name__=='__main__':main()
