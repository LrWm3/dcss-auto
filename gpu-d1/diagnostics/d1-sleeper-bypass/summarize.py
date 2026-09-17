"""Summarize fixed-endpoint results and map-cluster paired exit differences."""
import json
from pathlib import Path
import numpy as np
import torch
import runtime as r

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'learning-runs/d1-sleeper-bypass'

def read(p):return json.loads((BASE/p).read_text())

def main():
    torch.set_num_threads(1)
    report={'run':read('result.json'),'manifest':read('manifest.json'),'arms':{},'paired_exit_differences':{}}
    for arm in ['source','control','practice']:
        cell=report['arms'][arm]={}
        if arm!='source':
            cell['curve']=read(f'{arm}/curve.json')
            cell['completed_episodes']=read(f'{arm}/episode-counts-1000448.json')
        cell['practice_test']=read(f'eval/{arm}-practice.json')
        cell['ordinary_test']={}
        for panel in ['test_seen','test_unseen_enemies','ordinary']:
            for mode in ['sampled','greedy']:
                cell['ordinary_test'][panel+'_'+mode]=read(f'eval/{arm}-{panel}-{mode}.json')
    rng=np.random.default_rng(99121);draws=rng.integers(0,100,(10000,100))
    for key,baseline in report['arms']['control']['ordinary_test'].items():
        candidate=report['arms']['practice']['ordinary_test'][key]
        # Repeated episodes and player profiles share maps; cluster all by map.
        delta=sum(np.array(b['exits_by_map'])-np.array(a['exits_by_map']) for a,b in zip(baseline['profiles'],candidate['profiles']))
        denom=len(baseline['profiles'])*baseline['repeats']
        boot=delta[draws].mean(1)/denom
        report['paired_exit_differences'][key]={'practice_minus_control':float(delta.mean()/denom),'map_bootstrap_95_interval':np.quantile(boot,[.025,.975]).tolist()}
    report['caution']='One training seed. Intervals reflect held-out map sampling, not training-seed variability. Practice changes enemy count as well as geometry.'
    bank=torch.load(r.a.SUITE/'behavior/stalls.pt',weights_only=False)
    report['original_stall_action_probabilities']={}
    with torch.no_grad():
        for arm in ['source','control','practice']:
            path=r.SOURCE if arm=='source' else BASE/f'{arm}/checkpoints/1000448.pt'
            d=r.load_model(path)(bank['obs'].cuda(),bank['mask'].cuda())[0]
            report['original_stall_action_probabilities'][arm]={'states':len(bank['rows']),'mean_wait_probability':float(d.probs[:,16].mean()),'greedy_waits':int((d.greedy()==16).sum())}
    path=ROOT/'results/d1-sleeper-bypass-training.json';path.write_text(json.dumps(report,indent=2)+'\n');print(path)
    for arm,cell in report['arms'].items():
        print(arm,'practice',cell['practice_test'])
        print({k:{f:round(v[f],4) for f in ['exit_rate','death_rate','timeout_rate','turns']} for k,v in cell['ordinary_test'].items()})
    print('differences',report['paired_exit_differences'])

if __name__=='__main__':main()
