"""Read-only input interventions and exact bootstrap-sample audit."""
import os
os.environ['DCSS_REPRESENTATION']='spatial-v6'
import argparse,copy,json,hashlib
from collections import Counter,defaultdict
from pathlib import Path
import torch
from bootstrap_repair import read_training,sample_rows,write,dropout_recent_actions
from model import load_model,tensor_for_actions
from teacher import choose_action,_actions
import structured_features as f

def scores(model,state,variant='original'):
    s=copy.deepcopy(state)
    if variant=='no_history':s['history']=[]
    if variant=='last_move':
        for h in s.get('history',[]):h['action']={'kind':'MOVE','dx':1,'dy':0}
    if variant.startswith('hp_'):
        s['player']['hp']=s['player']['max_hp']*float(variant[3:])
    if variant=='turn_zero':s['turn']=0
    if variant=='history_only_presence':
        s['history']=[{'action':{}} for _ in s.get('history',[])]
    actions=_actions(s);x=tensor_for_actions(s,actions)
    if variant=='masked_commands':x=dropout_recent_actions(x)
    state_tensor,action_tensor=x
    if variant=='zero_global':state_tensor[:,:f.GLOBAL_DIM]=0
    if variant=='zero_grid':state_tensor[:,f.GLOBAL_DIM:f.GLOBAL_DIM+f.GRID_DIM]=0
    if variant=='zero_inventory':state_tensor[:,f.GLOBAL_DIM+f.GRID_DIM:]=0
    with torch.no_grad():logits=model(x);prob=logits.softmax(-1)
    i=int(logits.argmax());teacher=choose_action(s)
    moves=[j for j,a in enumerate(actions) if a['kind']=='MOVE']
    wait=next(j for j,a in enumerate(actions) if a['kind']=='WAIT')
    return {'kind':actions[i]['kind'],'index':i,'teacher_index':teacher,
            'wait_probability':float(prob[wait]),'move_probability':sum(float(prob[j]) for j in moves),
            'wait_over_best_move':float(logits[wait]-max(logits[j] for j in moves)) if moves else None}

def summarize(rows):
    kinds=Counter();seeds=Counter();wait_health=Counter();unique=Counter();seen=set()
    for r in rows:
        s=r['observation'];kind=_actions(s)[r['teacher_action_index']]['kind']
        kinds[kind]+=1;seeds[str(r['episode_seed'])+'/'+kind]+=1
        if kind=='WAIT':
            p=s['player'];wait_health['full' if p['hp']>=p['max_hp'] else 'injured']+=1
        # Deduplicate identical observable situations except time/history.
        stripped={k:v for k,v in s.items() if k not in ('history','turn','last_action_result')}
        key=hashlib.sha256(json.dumps(stripped,sort_keys=True).encode()).hexdigest()
        if key not in seen:unique[kind]+=1;seen.add(key)
    return {'rows':len(rows),'kinds':dict(kinds),'seeds_and_kinds':dict(seeds),
            'wait_health':dict(wait_health),'unique_without_time_history':dict(unique)}

def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True)
    p.add_argument('--source',type=Path,required=True);args=p.parse_args();root=args.run
    torch.set_num_threads(1);model,_=load_model(root/'round-00/model.pt')
    report={'cutoffs':[],'training':{}}
    variants=['original','masked_commands','no_history','last_move','history_only_presence',
              'hp_0.5','hp_0.99','hp_1.0','turn_zero','zero_global','zero_grid','zero_inventory']
    for r in json.loads((root/'round-00/validation/results.json').read_text()):
        s=json.loads((Path(r['resume_checkpoint'])/'case.json').read_text())['observation']
        item={'seed':r['seed'],'hp':s['player']['hp'],'max_hp':s['player']['max_hp'],
              'teacher':_actions(s)[choose_action(s)],'history':s.get('history'),
              'variants':{v:scores(model,s,v) for v in variants}}
        report['cutoffs'].append(item)
    write(root/'wait-diagnosis.json',report)
    print('ABLATIONS',json.dumps([{ 'seed':r['seed'],'variants':r['variants']} for r in report['cutoffs']]),flush=True)
    old=read_training(args.source/'replay');demos=read_training(root/'demonstrations')
    corrections=read_training(root/'round-00/corrections')
    combined=sample_rows(old+demos,limit=4096)
    selected=sample_rows(combined+corrections,limit=2048,seed=0)
    for name,rows in [('old',old),('demonstrations',demos),('corrections',corrections),('selected',selected)]:
        report['training'][name]=summarize(rows)
    # Whole selected dataset, not a training-accuracy mixture or a 128-row sample.
    confusion=Counter();correct=Counter();mismatch=0
    for r in selected:
        s=r['observation'];a=_actions(s);target=r['teacher_action_index']
        mismatch+=int(target!=choose_action(s))
        with torch.no_grad():i=int(model(tensor_for_actions(s,a)).argmax())
        confusion[a[target]['kind']+' -> '+a[i]['kind']]+=1
        if i==target:correct[a[target]['kind']]+=1
    report['training']['selected']['prediction_confusion']=dict(confusion)
    report['training']['selected']['exact_correct_by_kind']=dict(correct)
    report['training']['selected']['label_mismatches']=mismatch
    write(root/'wait-diagnosis.json',report)
    print('TRAINING',json.dumps(report['training']),flush=True)

if __name__=='__main__':main()
