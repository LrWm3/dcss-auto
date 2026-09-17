"""Compact counts, paired regressions, and correction-label acquisition."""
import json
import torch
import run


@torch.no_grad()
def main():
    torch.set_num_threads(1)
    result = json.loads((run.SUITE/'result.json').read_text())
    summary = dict(selections=result['selections'], cohorts={}, validation={}, correction_learning={})
    original = json.loads((run.ROOT/'results/d1-stairs-v2.json').read_text())['confirmation']['adapted']
    for mode in ['sampled','greedy']:
        for field in ['exit','death','timeout','turns','kills']:
            assert result['confirmation']['regression']['baseline'][mode]['outcomes'][field] == original[mode]['outcomes'][field]
    summary['original_baseline_reproduced'] = True
    summary['targeted_vs_control']={cohort:{mode:run.paired(models['targeted'][mode],models['control'][mode])
        for mode in ['sampled','greedy']} for cohort,models in result['confirmation'].items()}
    for arm,curve in result['curves'].items():
        summary['validation'][arm]=[dict(decisions=r['decisions'],training_seconds=r['training_seconds'],
            counts={m:{k:int(sum(r[m]['outcomes'][k])) for k in ['exit','death','timeout']} for m in ['sampled','greedy']}) for r in curve]
    for cohort,models in result['confirmation'].items():
        summary['cohorts'][cohort]={}
        for name,modes in models.items():
            summary['cohorts'][cohort][name]={}
            for mode,r in modes.items():
                b=models['baseline'][mode]['outcomes'];o=r['outcomes']
                row=dict(episodes=r['episodes'],exits=int(sum(o['exit'])),deaths=int(sum(o['death'])),
                    timeouts=int(sum(o['timeout'])),turns=r['turns'],exit_rate=r['exit_rate'],
                    former_deaths_now_exit=sum(d and e for d,e in zip(b['death'],o['exit'])),
                    new_deaths=sum(not d and e for d,e in zip(b['death'],o['death'])),
                    former_exits_now_fail=sum(e and not n for e,n in zip(b['exit'],o['exit'])))
                if name!='baseline':row.update(result['comparisons'][cohort][name][mode])
                summary['cohorts'][cohort][name][mode]=row
    bank=torch.load(run.SUITE/'bank.pt',map_location='cpu',weights_only=False)
    labels=torch.load(run.SUITE/'corrections.pt',map_location='cpu',weights_only=False)
    summary['data_preparation']=dict(deaths=bank['deaths'],saved_states=len(bank['obs']),
        collection_decisions=bank['collection_decisions'],retention_observations=len(bank['replay_obs']),
        candidate_checks=labels['reports'],accepted_states=labels['ids'].tolist())
    x=bank['obs'][labels['ids']].cuda();m=bank['mask'][labels['ids']].cuda();y=labels['actions'].cuda()
    model=run.load_model()
    probe=run.reseeder()
    summary['practice_outcomes']={}
    audit_path=run.ROOT/'learning-runs/d1-stairs-deaths/snapshots.pt'
    audit=torch.load(audit_path,map_location='cpu',weights_only=False) if audit_path.exists() else None
    summary['corridor_probe']={}
    for name in ['baseline','targeted','control']:
        step=result['selections'].get(name,0)
        path=run.SUITE/name/f'checkpoints/{step}.pt' if step else run.SOURCE
        model.load_state_dict(torch.load(path,map_location='cpu',weights_only=False)['model'])
        dist=model(x,m)[0]
        summary['correction_learning'][name]=dict(examples=len(y),greedy_matches=int((dist.greedy()==y).sum()),
            mean_target_probability=float(dist.probs.gather(1,y[:,None]).mean()))
        # New RNG after training, full greedy continuations, on the 20 fitted
        # scenes. This measures practice acquisition, not held-out performance.
        out=run.futures(model,bank,labels['ids'].repeat_interleave(64),
            dist.greedy().cpu().repeat_interleave(64),793115,probe)
        summary['practice_outcomes'][name]=dict(episodes=len(out),seed=793115,
            exits=int(out[:,0].sum()),deaths=int(out[:,1].sum()),timeouts=int(out[:,2].sum()),
            exit_rate=float(out[:,0].mean()),scope='Training scenes; fresh future RNG; full learned greedy continuation')
        if audit is not None:
            i=int(torch.where(audit['ids']==1607)[0].item())
            d=model(audit['obs'][0,i:i+1].cuda(),audit['mask'][0,i:i+1].cuda())[0]
            summary['corridor_probe'][name]=dict(episode=1607,greedy_action=int(d.greedy()[0]),
                move_e_probability=float(d.probs[0,1]),attack_nw_probability=float(d.probs[0,15]),
                note='Inference on the old fatal state only; not a new survival rollout or selection metric.')
    summary['preparation_seconds']=result['preparation_seconds']
    (run.ROOT/'results/d1-stairs-survival-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    # Keep every paired outcome, without multi-megabyte indentation overhead.
    (run.ROOT/'results/d1-stairs-survival.json').write_text(json.dumps(result,separators=(',',':'),allow_nan=False)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
