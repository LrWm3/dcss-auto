"""Verified one-axis character mutations and fresh V2 strategy labels. No fitting."""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor,as_completed
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from augmentation_dataset import read,inventory,classify,verify_result
from augment_encounters import POLICIES
from bench import HERE,ROOT,ENGINE,sha
from goal_env import GoalEnvironment
from goal_controllers import Controller
from rich_features import features,values
from rich_goals import derive,run
from run_goals import SOURCES
from train_encounters import write
from verify_resume import normalized

SOURCES_V2=SOURCES+('rich_goal_bridge.lua','rich_features.py','rich_goals.py',
                    'character_dataset.py','augmentation_dataset.py','verify_resume.py')


def validate(recipe):
    if set(recipe)!={'id','axis','name','value'}:raise ValueError('Invalid recipe fields')
    axis,name,v=recipe['axis'],recipe['name'],recipe['value']
    if type(v)!=int:raise ValueError('Integer mutation value required')
    allowed={'none':{'none'},'skill':{'Axes','Fighting','Armour','Dodging','Shields','Evocations'},
        'xl':{'xl'},'attribute':{'str','int','dex'},'gear':{'hand_axe','war_axe','robe','ring_mail','plate_armour'},
        'resistance':{'fire','cold','poison','electricity'}}
    if axis not in allowed or name not in allowed[axis]:raise ValueError('Unknown mutation')
    lo,hi={'none':(0,0),'skill':(-5,5),'xl':(-3,3),'attribute':(-6,6),
           'gear':(0,5),'resistance':(1,1)}[axis]
    if not lo<=v<=hi or (axis in ('skill','xl','attribute') and v==0):raise ValueError('Mutation out of bounds')
    if not recipe['id'].replace('-','').replace('_','').isalnum():raise ValueError('Unsafe recipe ID')


def canonical(s):
    s=normalized(s)
    for key in ('gear','enemy_details'):
        if key in s:s[key]=sorted(json.dumps(v,sort_keys=True) for v in values(s[key]))
    return s


def unchanged_world(before,after):
    for k in ('floor','position','turn'):assert before[k]==after[k],k
    # Threat/safety/reachability can legitimately change with character strength.
    mon=lambda s:sorted((e['name'],e['x'],e['y'],e['damage_level']) for e in values(s['enemy_details']))
    assert mon(before)==mon(after),'Enemies moved or changed wounds'
    terrain=lambda s:sorted((c['x'],c['y'],c['feature'],c.get('cloud')) for c in values(s['known']))
    assert terrain(before)==terrain(after),'Terrain/clouds changed'


def intent(before,after,r):
    unchanged_world(before,after)
    assert after['hp']==after['max_hp'] and after['hp']>0,'HP normalization'
    a,b=before['player'],after['player'];axis,name,v=r['axis'],r['name'],r['value']
    if axis=='skill':assert abs(b['skills'][name]-max(0,min(27,a['skills'][name]+v)))<.21,'Skill delta'
    elif axis=='xl':assert b['xl']==a['xl']+v,'XL delta'
    elif axis=='attribute':
        field={'str':'strength','int':'intelligence','dex':'dexterity'}[name]
        assert b[field]==a[field]+v,'Attribute delta'
    elif axis=='resistance':
        field={'fire':'res_fire','cold':'res_cold','poison':'res_poison','electricity':'res_shock'}[name]
        assert b[field]>a[field],'Resistance did not increase'
    elif axis=='gear':
        kind={'hand_axe':'hand axe','war_axe':'war axe','plate_armour':'plate armour',
              'ring_mail':'ring mail','robe':'robe'}[name]
        assert any(g.get('equipped') and g.get('subtype')==kind and g.get('plus')==v
                   for g in values(after['gear'])),'Gear preset'
    if axis!='none':assert features(before)!=features(after),'No observable feature effect'


def make_case(parent,case,recipe):
    validate(recipe);shutil.copytree(parent,case)
    source=(case/'trial.rc').read_text();at=source.rfind('\n>')
    if at<0 or 'you.tactical_augment(' in source:raise ValueError('Not an unaugmented rich parent')
    call='' if recipe['axis']=='none' else 'you.tactical_character(%s,%s,%d)' % (
        json.dumps(recipe['axis']),json.dumps(recipe['name']),recipe['value'])
    hook='''
local character_parent_ready=ready
local character_applied=false
function ready()
  if not character_applied then
    %s
    you.tactical_augment(100,0)
    character_applied=true
  end
  character_parent_ready()
end
''' % call
    (case/'trial.rc').write_text(source[:at]+hook+source[at:])
    m=read(case/'case.json');m.update(engine_sha256=sha(ENGINE),rc_sha256=sha(case/'trial.rc'),
        character_recipe=recipe,training_ready=False,replay_verified=False)
    write(case/'case.json',m)


def preflight(s,r):
    if s is None:return
    axis,name,v=r['axis'],r['name'],r['value'];p=s['player']
    if axis=='xl' and not 1<=p['xl']+v<=27:raise ValueError('Inapplicable XL bounds')
    if axis=='resistance':
        key={'fire':'res_fire','cold':'res_cold','poison':'res_poison','electricity':'res_shock'}[name]
        if p[key]>=(3 if name in ('fire','cold') else 1):raise ValueError('Resistance already capped')
    if axis=='skill' and p['skills'][name]==max(0,min(27,p['skills'][name]+v)):
        raise ValueError('Skill already at bound')
    if axis=='gear':
        slot='weapon' if name.endswith('axe') else 'body armour'
        equipped=[g for g in values(s['gear']) if g.get('equipped') and g.get('equip_type')==slot]
        if len(equipped)!=1 or equipped[0].get('artprops'):raise ValueError('Unsupported empty/artefact gear slot')


def reference(case,root,steps):
    env=GoalEnvironment(root);states=[];actions=[]
    try:
        s=env.reset(case);states.append(s);c=Controller('pursue',False)
        for _ in range(steps):
            if s.get('terminal'):break
            action=c(s);actions.append(action);s=env.step(action);states.append(s)
        write(root/'reference.json',dict(states=states,actions=actions,worker=str(env.work)))
    finally:env.close()


def family(e,cfg,root):
    work=root/e['id'];work.mkdir(parents=True,exist_ok=False)
    result=dict(id=e['id'],seed=e['seed'],split=e['split'],variants=[],status='failed')
    try:
        if shutil.disk_usage(root).free<15*1024**3:raise RuntimeError('Disk safety floor')
        parent=Path(e['case']);meta=read(parent/'case.json')
        assert meta['training_ready'] and e['split']=='train'
        assert sha(parent/'checkpoint.cs')==e['save_sha256'] and sha(parent/'trial.rc')==e['rc_sha256']
        rich=derive(parent,work/'rich-parent')
        # Compare unchanged new engine with old engine on identical actions.
        subprocess.run([sys.executable,str(Path(__file__).resolve()),'--reference',str(rich),
            str(work/'old-engine'),str(cfg['verify_steps'])],check=True,timeout=600,
            env={**os.environ,'DCSS_TACTICAL_ENGINE':str(ROOT/cfg['parent_engine'])},
            stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        ref=read(work/'old-engine/reference.json');m=read(rich/'case.json')
        m['engine_sha256']=sha(ENGINE);write(rich/'case.json',m)
        env=GoalEnvironment(work/'neutral')
        try:
            s=env.reset(rich);assert canonical(s)==canonical(ref['states'][0]),'Neutral initial mismatch'
            for action,t in zip(ref['actions'],ref['states'][1:]):
                s=env.step(action);assert canonical(s)==canonical(t),'Neutral trajectory mismatch'
            result['neutral']=dict(passed=True,worker=str(env.work),reference=str(work/'old-engine/reference.json'))
        finally:env.close()
        baseline=None
        for recipe in cfg['recipes']:
            vroot=work/recipe['id'];vroot.mkdir();case=vroot/'case'
            v=dict(id=e['id']+'/'+recipe['id'],recipe=recipe,case=str(case),rows=[],replay_verified=False)
            try:
                preflight(baseline,recipe)
                make_case(rich,case,recipe);trajectories=[];workers=[]
                v['workers']=workers
                for repeat in range(2):
                    env=GoalEnvironment(vroot/'verify')
                    try:
                        s=env.reset(case);states=[s];c=Controller('pursue',False)
                        for _ in range(cfg['verify_steps']):
                            if s.get('terminal'):break
                            s=env.step(c(s));states.append(s)
                        trajectories.append(states)
                    finally:
                        if hasattr(env,'work'):workers.append(str(env.work))
                        env.close()
                a,b=trajectories
                assert [canonical(s) for s in a]==[canonical(s) for s in b],'Repeated reset mismatch'
                if recipe['axis']=='none':baseline=a[0]
                assert baseline is not None,'Baseline must run first'
                intent(baseline,a[0],recipe)
                v.update(replay_verified=True,initial=a[0],workers=workers,
                    trace_sha256=[sha(Path(w)/'transitions.jsonl') for w in workers])
                for policy in ([] if cfg.get('verification_only') else POLICIES):
                    r=verify_result(run(dict(id=v['id'],seed=e['seed']),case,vroot/policy.replace(':','-'),policy,cfg['steps']))
                    r.update(split=e['split'],split_group=e['seed'],family_id=e['id'],recipe=recipe)
                    v['rows'].append(r)
            except Exception as exc:v['error']=repr(exc)
            v['label']=classify(v['rows']);result['variants'].append(v)
            write(work/'progress.json',result)
            print(json.dumps(dict(family=e['id'],recipe=recipe['id'],verified=v['replay_verified'],
                                  error=v.get('error'),outcomes=dict(Counter(r['outcome'] for r in v['rows'])))),flush=True)
            if recipe['axis']=='none' and not v['replay_verified']:raise RuntimeError('Baseline failed')
        result['status']='complete'
    except Exception as exc:
        result['error']=repr(exc)
        if isinstance(exc,subprocess.CalledProcessError):result['stderr']=exc.stderr.decode(errors='replace')
    write(work/'family.json',result);return result


def export(root,families):
    allrows=[];training=[];mixed=[];labels=[]
    for f in families:
        for v in f['variants']:
            checked=[verify_result(r) for r in v['rows']];label=classify(checked)
            labels.append(dict(id=v['id'],family_id=f['id'],seed=f['seed'],split=f['split'],
                recipe=v['recipe'],case=v['case'],replay_verified=v['replay_verified'],error=v.get('error'),**label))
            allrows+=checked
            if f['split']=='train' and v['replay_verified'] and label['complete']:
                selected=[r for r in checked if r['outcome'] in ('death','recovered_quiet')]
                training+=selected
                if label['mixed']:mixed+=selected
    for name,obj in [('results',allrows),('labels',labels),('training-rows',training),('mixed-training-rows',mixed)]:write(root/(name+'.json'),obj)
    summary=dict(families=len(families),family_status=dict(Counter(f['status'] for f in families)),
        variants=len(labels),verified=sum(l['replay_verified'] for l in labels),
        trials=len(allrows),outcomes=dict(Counter(r['outcome'] for r in allrows)),
        training_rows=len(training),mixed_training_rows=len(mixed),
        mixed_variants=sum(l['mixed'] for l in labels),
        verified_by_axis=dict(Counter(l['recipe']['axis'] for l in labels if l['replay_verified'])),
        training_seeds=sorted({r['seed'] for r in training}),fitting=False,production_export=False)
    write(root/'summary.json',summary);return summary


def main():
    if len(sys.argv)>1 and sys.argv[1]=='--reference':
        reference(Path(sys.argv[2]),Path(sys.argv[3]),int(sys.argv[4]));return
    p=argparse.ArgumentParser();p.add_argument('config',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();cfg=read(a.config);root=a.output.resolve()
    if ENGINE.name!='crawl-tactical-character' or os.environ.get('DCSS_TACTICAL_CHARACTER')!='1' or os.environ.get('DCSS_TACTICAL_AUGMENT')!='1':
        raise ValueError('Explicit character lab engine and both opt-ins required')
    for r in cfg['recipes']:validate(r)
    if len({r['id'] for r in cfg['recipes']})!=len(cfg['recipes']):raise ValueError('Duplicate recipe ID')
    if len(set(cfg['families']))!=len(cfg['families']):raise ValueError('Duplicate family ID')
    assert cfg['recipes'][0]['axis']=='none'
    entries=inventory(cfg);eligible={e['id']:e for e in entries if e['eligible'] and e['split']=='train'}
    selected=[eligible[i] for i in cfg['families']]
    root.mkdir(parents=True,exist_ok=False)
    manifest=dict(config=cfg,entries=selected,engine_sha256=sha(ENGINE),
        parent_engine_sha256=sha(ROOT/cfg['parent_engine']),sources={n:sha(HERE/n) for n in SOURCES_V2},
        inputs={n:sha(ROOT/n) for n in [cfg['partitions'],cfg['reservation']]+[d['index'] for d in cfg['datasets']]},
        fitting=False,production_export=False)
    write(root/'manifest.json',manifest);families=[]
    with ProcessPoolExecutor(max_workers=cfg['jobs']) as pool:
        for future in as_completed([pool.submit(family,e,cfg,root) for e in selected]):
            families.append(future.result());write(root/'coverage.json',families)
    for n,h in manifest['sources'].items():assert sha(HERE/n)==h,'Source changed during collection'
    for n,h in manifest['inputs'].items():assert sha(ROOT/n)==h,'Input changed during collection'
    assert sha(ENGINE)==manifest['engine_sha256'],'Engine changed during collection'
    print(json.dumps(export(root,families)),flush=True)


if __name__=='__main__':main()
