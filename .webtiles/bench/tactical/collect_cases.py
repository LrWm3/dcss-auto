"""Capture configured visible encounters and verify reset/uninterrupted fidelity.

Each case owns private workers and immutable saves. Failures remain evidence,
not successful episodes. No live webtiles sessions are controlled by this tool.
"""
import argparse
import concurrent.futures
import json
from pathlib import Path

from bench import Environment, ROOT, sha
from experiment import recovered
from verify_resume import normalized

SEEDS=['6144198052690956201','13772526223844354029','1760771545328102746',
       '17908030050512890810','103583508244309201']


def rollout(env,state,steps):
    states=[state];quiet=None
    for _ in range(steps):
        if state.get('terminal'):return states,'death'
        if recovered(state):
            if quiet is None:quiet=state['turn']
            if state['turn']-quiet>=10:return states,'safe_recovery'
        else:quiet=None
        state=env.step('baseline');states.append(state)
    return states,'death' if state.get('terminal') else 'budget'


def compare(a,b):
    differences=[i for i,(x,y) in enumerate(zip(a,b)) if normalized(x)!=normalized(y)]
    return dict(passed=len(a)==len(b) and not differences,
                lengths=[len(a),len(b)],first_difference=differences[0] if differences else None)


def collect(root,source,row):
    work=root/row['id'];work.mkdir()
    case=work/'case';seed=SEEDS[row['seed_index']-1]
    result=dict(id=row['id'],seed=seed,trigger=row['trigger'],source_rc_sha256=sha(source),
                reason=row['reason'],case=str(case),trials=[],training_ready=False)
    env=Environment(work,source_rc=source,seed=seed,capture_config=row['trigger'])
    try:
        meta=env.capture(case,row.get('warmup',0))
        result['initial']={k:v for k,v in meta['observation'].items()
                           if k in ('turn','floor','hp','max_hp','monsters','status')}
        trajectories=[]
        for mode in ('reset','reset_repeat','uninterrupted'):
            state=env.launch() if mode=='uninterrupted' else env.reset(case)
            if state.get('terminal'):
                raise RuntimeError(mode+' died before the capture trigger (no encounter trajectory)')
            if mode=='uninterrupted':
                for _ in range(row.get('warmup',0)):
                    state=env.step('baseline')
                    if state.get('terminal'):
                        raise RuntimeError('Uninterrupted replay died before the warmup boundary')
            states,outcome=rollout(env,state,row.get('steps',120))
            trajectories.append(states)
            if len(trajectories)==2:
                result['repeatability']=compare(trajectories[0],trajectories[1])
            result['trials'].append(dict(mode=mode,outcome=outcome,decisions=len(states)-1,
                worker=str(env.work),transitions_sha256=sha(env.work/'transitions.jsonl')))
            env.close()
        result['repeatability']=compare(trajectories[0],trajectories[1])
        result['uninterrupted_fidelity']=compare(trajectories[0],trajectories[2])
        result['training_ready']=result['repeatability']['passed'] and result['uninterrupted_fidelity']['passed']
        meta['fidelity']=result['uninterrupted_fidelity']
        meta['repeatability']=result['repeatability']
        meta['training_ready']=result['training_ready']
        (case/'case.json').write_text(json.dumps(meta,indent=2)+'\n')
    except Exception as exc:
        result.update(error=str(exc),failed_worker=str(getattr(env,'work','')))
    finally:
        env.close()
        (work/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('config',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--jobs',type=int,default=3)
    a=p.parse_args();cfg=json.loads(a.config.read_text())
    source=(ROOT/cfg['rc']).resolve()
    if cfg.get('rc_sha256') and sha(source)!=cfg['rc_sha256']:raise ValueError('Source RC mismatch')
    ids=[r['id'] for r in cfg['cases']]
    import re
    if len(ids)!=len(set(ids)) or not all(re.fullmatch(r'[a-z0-9-]+',i) for i in ids):
        raise ValueError('Case IDs must be unique safe path components')
    for row in cfg['cases']:
        if type(row['seed_index']) is not int or not 1<=row['seed_index']<=5:raise ValueError('Bad seed index')
        if type(row.get('steps',120)) is not int or row.get('steps',120)<1:raise ValueError('Bad step budget')
        if type(row.get('warmup',0)) is not int or row.get('warmup',0)<0:raise ValueError('Bad warmup')
    root=a.output.resolve();root.mkdir(parents=True,exist_ok=False)
    (root/'config.json').write_text(json.dumps(cfg,indent=2)+'\n')
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.jobs) as pool:
        results=list(pool.map(lambda row:collect(root,source,row),cfg['cases']))
    (root/'catalog.json').write_text(json.dumps(results,indent=2)+'\n')
    return 0 if all(r['training_ready'] for r in results) else 1


if __name__=='__main__':raise SystemExit(main())
