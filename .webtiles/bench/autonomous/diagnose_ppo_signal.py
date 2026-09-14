"""Read-only audit of saved PPO targets, sampling and critic observability."""
import train_ppo_pilot
import argparse
import copy
import gzip
import json
import statistics
from collections import Counter,defaultdict
from pathlib import Path
import torch
import numpy as np
from ppo_core import advantages
from model import tensor_for_actions
from teacher import _actions
from bootstrap_repair import write


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    torch.set_num_threads(1)
    reports=[];probe=None
    for cycle in sorted(args.source.glob('replicate-*/cycle-*')):
        rows=[]
        for path in sorted(cycle.glob('actors/*/trajectory.json.gz')):
            with gzip.open(path,'rt') as f:rows.extend(json.load(f))
        if not rows:continue
        if probe is None:probe=rows[0]['observation']
        aa,targets=advantages(rows)
        zero_values=[dict(r,value=0.,next_value=0.) for r in rows]
        reward_component,_=advantages(zero_values)
        value_component=np.array(aa)-np.array(reward_component)
        norm=(np.array(aa)-np.mean(aa))/max(np.std(aa),1e-6)
        actions=defaultdict(list); levels=Counter();segments=[];current=[]
        for i,r in enumerate(rows):
            action=_actions(r['observation'])[r['action_index']]
            key=action['kind']
            if key=='MELEE' and action.get('target_name') in ('bush','plant'):key='MELEE_FIREWOOD'
            actions[key].append(float(norm[i]));levels[r['observation'].get('level')]+=1
            current.append(r)
            if r['segment_end']:
                segments.append(current);current=[]
        truth=[];pred=[]
        for segment in segments:
            if segment[-1]['terminated']:
                tail=0.
                for r in reversed(segment):
                    tail+=r['reward'];truth.append(tail);pred.append(r['value'])
        variance=float(np.var(truth)) if truth else 0
        top_prob=[float(np.exp(r['log_probs']).max()) for r in rows]
        stairs=[r for r in rows if _actions(r['observation'])[r['action_index']]['kind']=='TAKE_STAIRS_DOWN']
        reports.append({'cycle':str(cycle.relative_to(args.source)),'decisions':len(rows),
            'fraction_top_action_over_99pct':sum(p>.99 for p in top_prob)/len(rows),
            'stairs_immediate_scaled_reward':sum(r['reward'] for r in stairs),
            'stairs_immediate_native_score_change':sum(r['native_after']-r['native_before'] for r in stairs),
            'levels':dict(levels),'segments':len(segments),
            'terminal_segments':sum(s[-1]['terminated'] for s in segments),
            'positive_rewards':sum(r['reward']>0 for r in rows),
            'negative_rewards':sum(r['reward']<0 for r in rows),
            'mean_abs_reward_advantage':float(np.mean(np.abs(reward_component))),
            'mean_abs_value_advantage':float(np.mean(np.abs(value_component))),
            'value_only_sign_disagreements':sum((a>0)!=(b>0) for a,b in zip(aa,reward_component)),
            'mc_terminal_states':len(truth),
            'critic_mse_terminal_segments':float(np.mean((np.array(pred)-np.array(truth))**2)) if truth else None,
            'critic_explained_variance_terminal_segments':1-float(np.var(np.array(pred)-np.array(truth)))/variance if variance>0 else None,
            'critic_mean_terminal_segments':statistics.mean(pred) if pred else None,
            'actual_remaining_score_mean_terminal_segments':statistics.mean(truth) if truth else None,
            'normalized_advantage_by_action':{k:{'n':len(v),'mean':statistics.mean(v),'positive_fraction':sum(x>0 for x in v)/len(v)} for k,v in actions.items()}})
    changed=copy.deepcopy(probe)
    changed['visit_memory']['since_discovery']=100
    changed['visit_memory']['since_new_tile']=100
    changed['visit_memory']['tiles']['0:0']=[9999,0]
    old_x=tensor_for_actions(probe,_actions(probe));new_x=tensor_for_actions(changed,_actions(changed))
    proof={'state_tensor_identical_when_visit_memory_changes':torch.equal(old_x[0],new_x[0]),
           'policy_action_tensor_changes':not torch.equal(old_x[1],new_x[1]),
           'critic_action_input':'always zero; visit-memory and action-route features therefore unavailable',
           'gae_reward_weight_after_100_decisions':.95**100,
           'interpretation':'not a hard horizon: accurate critic values can propagate longer-term outcomes'}
    write(args.output,{'cycles':reports,'observability_probe':proof,
          'caveat':'completed-segment critic audit is death-conditioned; not an unbiased calibration sample'})
    print(json.dumps({'observability':proof,'cycles':[{k:r[k] for k in ['cycle','levels','terminal_segments','mean_abs_reward_advantage','mean_abs_value_advantage','critic_explained_variance_terminal_segments']} for r in reports]},indent=2))


if __name__=='__main__':main()
