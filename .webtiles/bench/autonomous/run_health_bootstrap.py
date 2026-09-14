"""Bounded health-aware bootstrap, followed by diagnostic and live gates."""
import os
os.environ['DCSS_REPRESENTATION']='spatial-v6'
os.environ['DCSS_HEALTH_FEATURES']='1'
import argparse,copy,gzip,json
from pathlib import Path
import torch
from bootstrap_repair import read_training,sample_rows,fit,write,play_batch,navigation_gate
from model import ActionValueModel,load_model,save_model,tensor_for_actions
from teacher import choose_action,_actions
from data_split import assert_training_seed
import structured_features as f
import storage

def migrate(initial):
    payload=torch.load(initial,map_location='cpu',weights_only=False)
    if payload['feature_version']!='general-features-v6-spatial-entities':
        raise ValueError('explicit migration requires a legacy V6 checkpoint')
    model=ActionValueModel(hidden=payload['hidden']);weights=payload['state_dict'].copy()
    at=f.GLOBAL_DIM-4-(1+4*(1+len(f.KINDS)+6+129))
    for key in ('net.globals.0.weight','value_net.globals.0.weight'):
        old=weights[key]
        if old.shape[1]!=f.GLOBAL_DIM-4:raise ValueError('unexpected legacy global dimensions')
        weights[key]=torch.cat((old[:,:at],torch.zeros(old.shape[0],4),old[:,at:]),dim=1)
        # Newly inserted features have zero initial effect, not random effects.
        x=torch.arange(old.shape[1],dtype=old.dtype)[None,:]/old.shape[1]
        new_x=torch.cat((x[:,:at],torch.ones(1,4),x[:,at:]),dim=1)
        torch.testing.assert_close(x@old.T,new_x@weights[key].T,atol=1e-5,rtol=1e-5)
    model.load_state_dict(weights);model.eval();return model

def boundaries(directory):
    result=[]
    for path in sorted(Path(directory).glob('*.jsonl.gz')):
        plain=path.with_suffix('')
        if not plain.with_suffix('.result.json').exists():continue
        previous=None;count=0
        with gzip.open(path,'rt') as stream:
            for line in stream:
                row=json.loads(line);assert_training_seed(row.get('episode_seed'))
                if row.get('data_role','training')!='training':raise ValueError('non-training boundary')
                s=row.get('observation',{});p=s.get('player',{});a=_actions(s)
                label=row.get('teacher_action_index')
                if label is None:previous=None;continue
                if previous and count<12:
                    old=previous['observation'];q=old['player']
                    if (row['step']==previous['step']+1 and s['level']==old['level'] and
                        q['hp']<q['max_hp'] and p['hp']==p['max_hp'] and
                        _actions(old)[previous['teacher_action_index']]['kind']=='WAIT' and
                        a[label]['kind']!='WAIT'):
                        result.extend([previous,row]);count+=1
                previous={k:row[k] for k in ('observation','teacher_action_index','episode_seed','data_role','step') if k in row}
    return result

def health_check(model,source):
    results=[]
    for r in json.loads((source/'round-00/validation/results.json').read_text()):
        checkpoint=Path(r['resume_checkpoint'])
        if not checkpoint.is_absolute():checkpoint=Path(__file__).resolve().parents[3]/checkpoint
        s=json.loads((checkpoint/'case.json').read_text())['observation']
        item={'seed':r['seed'],'variants':{}}
        for mode in ('full','injured'):
            state=copy.deepcopy(s);p=state['player']
            p['hp']=p['max_hp'] if mode=='full' else max(1,p['max_hp']//2)
            state['hp']=[p['hp'],p['max_hp']];a=_actions(state)
            with torch.no_grad():i=int(model(tensor_for_actions(state,a)).argmax())
            target=choose_action(state)
            item['variants'][mode]={'teacher_kind':a[target]['kind'],'chosen_kind':a[i]['kind'],
                                    'correct_kind':a[target]['kind']==a[i]['kind']}
        results.append(item)
    passed=sum(all(v['correct_kind'] for v in r['variants'].values()) for r in results)
    return {'passed':len(results)==5 and passed>=4,'correct_pairs':passed,'total':len(results),'results':results}

def main():
    p=argparse.ArgumentParser();p.add_argument('--source',required=True,type=Path)
    p.add_argument('--replay-run',required=True,type=Path);p.add_argument('--initial',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path);p.add_argument('--smoke',action='store_true');args=p.parse_args()
    for name in ('source','replay_run','initial','output'):
        setattr(args,name,getattr(args,name).resolve())
    torch.set_num_threads(1);torch.manual_seed(17);root=args.output
    root.mkdir(parents=True,exist_ok=True);storage.configure(root)
    config={k:str(v.resolve()) if isinstance(v,Path) else v for k,v in vars(args).items()}
    if (root/'config.json').exists() and json.loads((root/'config.json').read_text())!=config:
        raise ValueError('resume config mismatch')
    write(root/'config.json',config)
    if (root/'status.json').exists():
        old=json.loads((root/'status.json').read_text())
        if old.get('phase') in ('complete','needs_review','smoke_complete'):print(old);return
    initial=root/'initial.pt';checkpoint=root/'candidate.pt'
    if not initial.exists():save_model(initial,migrate(args.initial),{'migration_from':str(args.initial)})
    if not checkpoint.exists():
        write(root/'status.json',{'phase':'loading_training_data'})
        rows=(read_training(args.source/'demonstrations',limit=16) if args.smoke else
              read_training(args.replay_run/'replay')+read_training(args.source/'demonstrations')+
              read_training(args.source/'round-00/corrections'))
        # Teacher actions bootstrap behavior; do not specially amplify the
        # teacher's "heal immediately in place" preference.
        rows=sample_rows(rows,limit=2048,seed=17)
        model,_=load_model(initial)
        write(root/'status.json',{'phase':'fitting','rows':len(rows),'boundary_rows':0})
        metrics=fit(model,rows,17,epochs=1 if args.smoke else 12,
                    learning_rate=3e-4,limit=16 if args.smoke else 2048)
        metrics['boundary_rows']=0
        write(root/'training.json',metrics);save_model(checkpoint,model,metrics)
    else:model,_=load_model(checkpoint)
    write(root/'status.json',{'phase':'checking_health_sensitivity'})
    check=health_check(model,args.source);check['acceptance_gate']=False
    write(root/'health_check.json',check)
    if args.smoke:
        write(root/'status.json',{'phase':'smoke_complete','health_check':check});return
    from rollout_liveness import rollout_check
    write(root/'status.json',{'phase':'checking_rollout_liveness'})
    activity=rollout_check(checkpoint,args.source,root/'rollout_check')
    if not activity['passed']:
        write(root/'status.json',{'phase':'needs_review','reason':'rollout_liveness','rollout_check':activity});return
    seeds=[str((0xE<<60)+60914000+i) for i in range(5)]
    for name,path in [('baseline',initial),('candidate',checkpoint)]:
        write(root/'status.json',{'phase':'live_validation','policy':name})
        results=play_batch(root/name,path,seeds,False)
        write(root/name/'gate.json',navigation_gate(results))
    write(root/'status.json',{'phase':'complete','promoted':False,
          'candidate_gate':json.loads((root/'candidate/gate.json').read_text())})

if __name__=='__main__':main()
