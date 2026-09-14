"""Bounded DAgger bootstrap repair and independent navigation acceptance gate.

Teacher labels are used only during bootstrap, including on policy-generated
training states. Validation episodes never enter the fitting data.
"""
import math
import time
import concurrent.futures
import gzip
import json
import random
from collections import defaultdict
from pathlib import Path
import torch
from collect import run_episode
from data_split import assert_training_seed
from model import load_model, save_model
from train_model import FeatureCache, _actions
import storage

VERSION='bootstrap-history-dropout-dagger-v3-natural-frequency'
VALIDATION_SEEDS=[str((0xE<<60)+60912000+i) for i in range(5)]


def write(path,obj):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n');temp.replace(path)


def dropout_recent_actions(features):
    """Hide recent command identity/direction; retain hazards, HP and failures."""
    from structured_features import GLOBAL_DIM, KINDS
    state,actions=features
    state=state.clone()
    record_dim=1+len(KINDS)+6+129
    start=GLOBAL_DIM-4*record_dim
    for i in range(4):
        at=start+i*record_dim
        state[:,at+1:at+1+len(KINDS)+2]=0
    return state,actions


def sample_rows(rows,limit=2048,seed=0):
    """Reserve rare action coverage without equalizing MOVE and WAIT counts."""
    rng=random.Random(seed);groups=defaultdict(list)
    for row in rows:
        assert_training_seed(row.get('episode_seed'))
        if row.get('data_role','training')!='training':
            raise ValueError('validation row in bootstrap data')
        state=row.get('observation',{});actions=_actions(state)
        target=row.get('teacher_action_index')
        if target is None and row.get('policy_version') in ('teacher','bootstrap'):
            target=row.get('action_index')
        if target is None or not 0<=target<len(actions):continue
        groups[actions[target]['kind']].append({**row,'teacher_action_index':target})
    for group in groups.values():rng.shuffle(group)
    sample=[]
    for key in sorted(groups,key=lambda k:(len(groups[k]),k)):
        sample.extend(groups[key][:min(8,len(groups[key]))])
        del groups[key][:min(8,len(groups[key]))]
    remaining=[row for group in groups.values() for row in group]
    rng.shuffle(remaining)
    return (sample+remaining)[:limit]


def read_training(directory,limit=4096):
    # Bound observation memory while retaining data across shards.
    if limit<1:raise ValueError('training sample limit must be positive')
    rng=random.Random(91);sample=[];n=0
    rare=defaultdict(list);kind_seen=defaultdict(int)
    for file in sorted(Path(directory).glob('*.jsonl*')):
        if file.suffix not in ('.gz','.jsonl') or 'counterfactual' in file.name:continue
        plain=file.with_suffix('') if file.suffix=='.gz' else file
        if not plain.with_suffix('.result.json').exists():continue
        opener=gzip.open if file.suffix=='.gz' else open
        with opener(file,'rt') as stream:
            for line in stream:
                row=json.loads(line)
                if not row.get('observation') or row.get('teacher_action_index') is None:continue
                assert_training_seed(row.get('episode_seed'))
                if row.get('data_role','training')!='training':raise ValueError('non-training replay')
                row={k:row[k] for k in ('observation','episode_seed','data_role','teacher_action_index') if k in row}
                actions=_actions(row['observation']);target=row['teacher_action_index']
                if not 0<=target<len(actions):raise ValueError('invalid teacher action index')
                kind=actions[target]['kind'];kind_seen[kind]+=1
                bucket=rare[kind]
                if len(bucket)<8:bucket.append(row)
                else:
                    j=rng.randrange(kind_seen[kind])
                    if j<8:bucket[j]=row
                n+=1
                if len(sample)<limit:sample.append(row)
                else:
                    i=rng.randrange(n)
                    if i<limit:sample[i]=row
    # A uniform reservoir alone can drop *every* stairs/consumable example.
    # Reserve a few examples per observed action kind, then fill with coverage.
    reserved=[]
    for i in range(8):
        for kind in sorted(rare,key=lambda k:(kind_seen[k],k)):
            if i<len(rare[kind]):reserved.append(rare[kind][i])
    seen=set();result=[]
    for row in reserved+sample:
        if id(row) in seen:continue
        seen.add(id(row));result.append(row)
        if len(result)==limit:break
    return result


def fit(model,rows,seed,epochs=3,learning_rate=1e-4,limit=2048,history_dropout=.5):
    if not 0<=history_dropout<=1 or epochs<1 or limit<1 or learning_rate<=0:
        raise ValueError('invalid bootstrap fitting configuration')
    rng=random.Random(seed);torch.manual_seed(seed)
    sample=sample_rows(rows,limit=limit,seed=seed)
    if not sample:raise ValueError('no bootstrap labels')
    optimizer=torch.optim.AdamW(model.net.parameters(),lr=learning_rate,weight_decay=1e-4)
    cache=FeatureCache();losses=[]
    model.train()
    for epoch in range(epochs):
        rng.shuffle(sample);loss_sum=0;correct=0
        for start in range(0,len(sample),16):
            batch=sample[start:start+16];optimizer.zero_grad()
            for row in batch:
                x=cache.get(row['observation'])
                if rng.random()<history_dropout:x=dropout_recent_actions(x)
                logits=model(x)
                target=int(row['teacher_action_index'])
                loss=torch.nn.functional.cross_entropy(logits[None,:],torch.tensor([target]),label_smoothing=.02)
                (loss/len(batch)).backward()
                loss_sum+=float(loss.detach());correct+=int(logits.argmax()==target)
            torch.nn.utils.clip_grad_norm_(model.net.parameters(),1.)
            optimizer.step()
        losses.append({'loss':loss_sum/len(sample),'accuracy':correct/len(sample)})
    model.eval()
    diagnostics={}
    # Report ordinary inference separately: mixed/dropout training accuracy can
    # hide a policy that succeeds only when recent command history is removed.
    for masked in (False,True):
        correct=0;counts=defaultdict(lambda: [0,0])
        for row in sample[:128]:
            x=cache.get(row['observation'])
            if masked:x=dropout_recent_actions(x)
            with torch.no_grad():pred=int(model(x).argmax())
            target=int(row['teacher_action_index']);ok=int(pred==target)
            correct+=ok;kind=_actions(row['observation'])[target]['kind']
            counts[kind][0]+=ok;counts[kind][1]+=1
        diagnostics['masked' if masked else 'original']={
            'rows':min(128,len(sample)),'accuracy':correct/min(128,len(sample)),
            'correct_total_by_teacher_kind':dict(counts)}
    return {'version':VERSION,'rows':len(sample),'epochs':epochs,'batch_size':16,
            'learning_rate':learning_rate,'history_action_dropout':history_dropout,'epochs_metrics':losses,
            'training_sample_inference':diagnostics}


def navigation_gate(results):
    valid=len(results)==5 and len({r.get('seed') for r in results})==5 and all(
        'error' not in r and isinstance(r.get('score'),(float,int)) and math.isfinite(r['score']) for r in results)
    descents=sum(r.get('action_counts',{}).get('TAKE_STAIRS_DOWN',0)>0 for r in results)
    stalled=sum(r.get('truncated',False) and r.get('action_counts',{}).get('WAIT',0)>
                .8*max(1,r.get('steps',0)) for r in results)
    return {'accepted':valid and descents>=2 and stalled<=1,
            'valid':valid,'games_with_deliberate_descent':descents,'wait_dominated_cutoffs':stalled,
            'required_descents':2,'maximum_wait_dominated_cutoffs':1}


def play_batch(root,model,seeds,training,steps=2000):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    def run(i,seed):
        result_file=root/f'episode-{i}.result.json'
        if result_file.exists():
            result=json.loads(result_file.read_text())
            if result['seed']!=str(seed):raise ValueError('resume seed mismatch')
            return result
        replay=root/f'episode-{i}.jsonl' if training else None
        if replay and replay.exists():
            replay.rename(replay.with_name(replay.name+f'.incomplete-{time.time_ns()}'))
        result=run_episode(root/f'game-{i}',seed,steps,replay_path=replay,
                           model_path=model,epsilon=0,snapshot=False,total_steps=steps,
                           data_role='training' if training else 'screen')
        if replay and replay.exists():storage.compress(replay)
        write(result_file,result)
        return result
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        results=list(pool.map(lambda pair:run(*pair),enumerate(seeds)))
    write(root/'results.json',results)
    return results


def repair(root,initial,rows,max_rounds=3,validation_seeds=None,seed_offset=0):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    validation_seeds=VALIDATION_SEEDS if validation_seeds is None else list(validation_seeds)
    from data_split import held_out_seed
    if len(validation_seeds)!=5 or len(set(validation_seeds))!=5 or not all(map(held_out_seed,validation_seeds)):
        raise ValueError('bootstrap validation requires five unique reserved held-out seeds')
    if max_rounds<1 or seed_offset<0:raise ValueError('invalid bootstrap run limits')
    config={'initial':str(Path(initial).resolve()),'validation_seeds':validation_seeds,
            'seed_offset':seed_offset,'max_rounds':max_rounds,'version':VERSION}
    config_file=root/'repair_config.json'
    if config_file.exists() and json.loads(config_file.read_text())!=config:
        raise ValueError('bootstrap resume configuration differs; use a new output directory')
    write(config_file,config)
    state_file=root/'status.json'
    if state_file.exists():
        previous=json.loads(state_file.read_text())
        if previous.get('phase')=='accepted':return Path(previous['checkpoint'])
        if previous.get('phase')=='needs_review':raise RuntimeError('Bootstrap gate failed; inspect '+str(state_file))
    if not (root/'baseline/results.json').exists():
        write(state_file,{'phase':'baseline_validation','checkpoint':str(initial)})
        results=play_batch(root/'baseline',initial,validation_seeds,False)
        write(root/'baseline/gate.json',navigation_gate(results))
    if not (root/'demonstrations/results.json').exists():
        write(state_file,{'phase':'collecting_demonstrations'})
        seeds=[str((0xA<<60)+60912100+seed_offset+i) for i in range(3)]
        play_batch(root/'demonstrations',None,seeds,True,steps=2000)
    rows=sample_rows(rows+read_training(root/'demonstrations'),limit=4096)
    for round_ in range(max_rounds):
        target=root/f'round-{round_:02d}';target.mkdir(exist_ok=True)
        checkpoint=target/'model.pt'
        if not checkpoint.exists():
            parent=Path(initial) if round_==0 else root/f'round-{round_-1:02d}'/'model.pt'
            model,_=load_model(parent)
            write(state_file,{'phase':'collecting_corrections','round':round_,'parent':str(parent)})
            if not (target/'corrections/results.json').exists():
                seeds=[str((0xA<<60)+60912000+seed_offset+round_*3+i) for i in range(3)]
                play_batch(target/'corrections',parent,seeds,True,steps=1000)
            corrections=read_training(target/'corrections')
            write(state_file,{'phase':'fitting','round':round_,'correction_rows':len(corrections)})
            metrics=fit(model,rows+corrections,round_,epochs=12,learning_rate=3e-4)
            save_model(checkpoint,model,{'bootstrap_repair':metrics,'source':str(parent)})
            write(target/'training.json',metrics)
        write(state_file,{'phase':'validating','round':round_,'checkpoint':str(checkpoint)})
        result_file=target/'validation/results.json'
        results=(json.loads(result_file.read_text()) if result_file.exists() else
                 play_batch(target/'validation',checkpoint,validation_seeds,False))
        gate=navigation_gate(results);write(target/'gate.json',gate)
        if gate['accepted']:
            write(state_file,{'phase':'accepted','round':round_,'checkpoint':str(checkpoint.resolve()),'gate':gate})
            return checkpoint
        rows=sample_rows(rows+read_training(target/'corrections'),limit=4096,seed=round_)
    write(state_file,{'phase':'needs_review','round':max_rounds-1,'gate':gate})
    raise RuntimeError('Bootstrap failed navigation gate; RL not launched: '+str(state_file))
