"""Opt-in rich observation/selector adapter; historical V1 stays unchanged."""
from collections import Counter
from pathlib import Path
import shutil
from augmentation_dataset import read
from bench import HERE, sha
from goal_env import GoalEnvironment, derive as derive_goal
from goal_controllers import Controller, Recovery
from rich_features import VERSION, features
from run_goals import options, fit as fit_weights
from train_encounters import write, value


def derive(parent,destination):
    parent=Path(parent);destination=Path(destination);meta=read(parent/'case.json')
    if meta.get('rich_version'):raise ValueError('Already a rich checkpoint')
    if not meta.get('goal_version'):
        derive_goal(parent,destination)
    else:
        for name,key in [('checkpoint.cs','save_sha256'),('trial.rc','rc_sha256')]:
            if sha(parent/name)!=meta[key]:raise ValueError('Parent changed')
        shutil.copytree(parent,destination)
    meta=read(destination/'case.json');source=(destination/'trial.rc').read_text()
    at=source.rfind('\n>')
    if at<0:raise ValueError('Missing Lua block')
    (destination/'trial.rc').write_text(source[:at]+'\n'+(HERE/'rich_goal_bridge.lua').read_text()+source[at:])
    meta.update(rich_version=VERSION,training_ready=False,replay_verified=False,
        rich_parent=str(parent.resolve()),rich_bridge_sha256=sha(HERE/'rich_goal_bridge.lua'),
        rc_sha256=sha(destination/'trial.rc'))
    write(destination/'case.json',meta);return destination


def fit(rows,epochs=1500):
    if not rows or any(r.get('feature_version')!=VERSION or
        r.get('feature_source_sha256')!=sha(HERE/'rich_features.py') or
        r.get('rich_bridge_sha256')!=sha(HERE/'rich_goal_bridge.lua') or
        r.get('split')!='train' or not r.get('evidence_verified') or
        r.get('outcome') not in ('death','recovered_quiet') for r in rows):
        raise ValueError('Only audited rich-v2 training rows may be fitted')
    return dict(feature_version=VERSION,feature_source_sha256=sha(HERE/'rich_features.py'),
                rich_bridge_sha256=sha(HERE/'rich_goal_bridge.lua'),
                weights=fit_weights(rows,epochs))


def select(model,s):
    if (model.get('feature_version')!=VERSION or
        model.get('feature_source_sha256')!=sha(HERE/'rich_features.py') or
        model.get('rich_bridge_sha256')!=sha(HERE/'rich_goal_bridge.lua')):
        raise ValueError('Model/feature schema mismatch: retrain explicitly')
    f=features(s)
    return max(options(s),key=lambda o:value(model['weights'],o,f))


def run(entry,case,root,option,steps=600,model=None):
    root=Path(root);root.mkdir(parents=True,exist_ok=False);env=GoalEnvironment(root)
    r=dict(case_id=entry['id'],seed=entry['seed'],option=option,
           feature_source_sha256=sha(HERE/'rich_features.py'),
           rich_bridge_sha256=sha(HERE/'rich_goal_bridge.lua'),
           feature_version=VERSION,outcome='harness_error',decisions=0)
    try:
        if read(Path(case)/'case.json').get('rich_bridge_sha256')!=r['rich_bridge_sha256']:
            raise ValueError('Checkpoint observation bridge changed; derive a new version')
        s=env.reset(case);first=s['turn'];r.update(features=features(s),available=options(s))
        if model is not None:option=select(model,s);r['option']=option
        if option not in options(s):r['outcome']='masked';return r
        g,b=option.split(':');controller=Controller(g,bool(int(b)));recovery=Recovery()
        noops=stagnant=0;counts=Counter()
        for i in range(steps):
            action=controller(s);counts[action]+=1;t=env.step(action);r['decisions']=i+1
            if t.get('terminal')=='death':r['outcome']='death';s=t;break
            noops=noops+1 if t['turn']==s['turn'] else 0
            stagnant=stagnant+1 if all(t[k]==s[k] for k in ('hp','floor','position','monsters')) else 0
            good=recovery.observe(s,t);s=t
            if good:r['outcome']='recovered_quiet';break
            if noops>=8:r['outcome']='no_turn_stall';break
            if stagnant>=80:r['outcome']='unresolved_stall';break
            if s['turn']-first>=1500:r['outcome']='budget_truncated';break
        else:r['outcome']='budget_truncated'
        r.update(final_floor=s.get('floor'),final_hp=s.get('hp'),quiet_turns=recovery.quiet,
                 turns=s.get('turn',first)-first,actions=dict(counts),events=controller.events,
                 credit={'death':-1.,'recovered_quiet':1.}.get(r['outcome'],0.))
    except Exception as exc:r['error']=repr(exc)
    finally:
        r['worker']=str(getattr(env,'work',root));env.close();write(root/'result.json',r)
    return r
