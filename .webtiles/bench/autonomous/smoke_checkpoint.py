"""Compare uninterrupted, in-place-save, and save/quit/restored combat traces."""
import argparse
import json
import os
from pathlib import Path
import time
from general_env import GeneralEnvironment, ENGINE, sha
from teacher import choose_action


def check(actual, expected, label):
    # Death evidence refers to each worker's own morgue; all gameplay fields
    # (including every exported non-UI RNG state) are compared unchanged.
    omit = {'evidence','evidence_sha256'}
    left = {k:v for k,v in actual.items() if k not in omit}
    right = {k:v for k,v in expected.items() if k not in omit}
    if left != right:
        differences = {k:{'actual':left.get(k),'expected':right.get(k)}
                       for k in left.keys() | right.keys() if left.get(k)!=right.get(k)}
        raise AssertionError(json.dumps({'label':label,'differences':differences}))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('output',type=Path)
    p.add_argument('--seed',default='1760771545328102746')
    p.add_argument('--steps',type=int,default=200)
    p.add_argument('--old-reference',type=Path)
    a = p.parse_args()
    os.environ['DCSS_GENERAL_RNG_DIAGNOSTICS'] = '1'
    a.output.mkdir(parents=True,exist_ok=False)
    env = GeneralEnvironment(a.output/'control',seed=a.seed)
    observations, actions = [], []
    try:
        state = env.launch()
        assert state.get('snapshot_in_place'), 'new engine required'
        observations.append(state)
        for _ in range(a.steps):
            if state.get('terminal'):
                break
            action = state['actions'][choose_action(state)]
            actions.append(action)
            state = env.step(action)
            observations.append(state)
    finally:
        env.close()
    old_trace_actions = 0
    if a.old_reference:
        reference = next(r for r in json.loads(a.old_reference.read_text())['runs'] if r['seed']==a.seed)
        ignored = {'rng_state','snapshot_in_place'}
        for i,other in enumerate(reference['observations']):
            check({k:v for k,v in observations[i].items() if k not in ignored},
                  {k:v for k,v in other.items() if k not in ignored}, f'old-engine:{i}')
        old_trace_actions = len(reference['actions'])
    combat = [i for i,s in enumerate(observations[:-1]) if s.get('monsters')]
    points = sorted(set([0,min(20,len(actions)-1)] + combat[:2] + combat[-1:]))
    results = []
    for mode in ('in_place','legacy'):
        env = GeneralEnvironment(a.output/mode,seed=a.seed)
        times, restored_actions = [], 0
        try:
            state = env.launch()
            check(state,observations[0],mode+':initial')
            for i,action in enumerate(actions):
                if i in points:
                    case = a.output/f'{mode}-case-{i}'
                    pid = env.child.pid
                    start = time.perf_counter()
                    metadata = env.save_state(case,in_place=mode=='in_place')
                    if mode=='legacy':
                        state = env.launch(case)
                    else:
                        assert env.child.pid==pid and env.child.isalive()
                    times.append(time.perf_counter()-start)
                    check(state,observations[i],f'{mode}:saved:{i}')
                    # Independently load the actual copied save, including the
                    # normal restored-game greeting, and replay future actions.
                    clone = GeneralEnvironment(a.output/f'{mode}-clone-{i}')
                    try:
                        other = clone.launch(case)
                        check(other,observations[i],f'{mode}:restored:{i}')
                        for j in range(i,min(i+8,len(actions))):
                            other = clone.step(actions[j])
                            check(other,observations[j+1],f'{mode}:clone:{j}')
                            restored_actions += 1
                    finally:
                        clone.close()
                state = env.step(action)
                check(state,observations[i+1],f'{mode}:continued:{i}')
        finally:
            env.close()
        results.append(dict(mode=mode,checkpoint_seconds=times,
                            continued_actions=len(actions),restored_actions=restored_actions))
    report = dict(engine_sha256=sha(ENGINE),seed=a.seed,combat_boundaries=len(combat),
                  old_engine_trace_actions=old_trace_actions,
                  checkpoint_positions=points,matched=True,results=results)
    (a.output/'results.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report))


if __name__=='__main__':
    main()
