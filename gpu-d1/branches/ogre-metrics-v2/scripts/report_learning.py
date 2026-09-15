#!/usr/bin/env python3
"""Evaluate frozen final checkpoints on a fresh suite and archive compact results."""
import argparse
import json
import pathlib
import shutil
import time
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import torch
from learn_env import Env, ROOT
from train_clear import Policy, evaluate

def plot_curves(curves, baselines, output):
    fig,axes=plt.subplots(1,3,figsize=(13,3.8))
    for curve in curves:
        xs=[r['decisions'] for r in curve]
        label=f"seed {curve[0]['seed']}"
        for ax,metric in zip(axes,('clear_rate','killed_fraction','mean_hp')):
            ax.plot(xs,[r['sampled'][metric] for r in curve],marker='o',label=label)
    for ax,metric,title in zip(axes,('clear_rate','killed_fraction','mean_hp'),
                               ('Floor-clear rate','Fraction of enemies killed','HP at episode end')):
        for row in baselines:
            if row['mode']!='wait':
                ax.axhline(row[metric],color='gray',linestyle='--' if row['mode']=='random' else ':',
                           label=row['mode'])
        ax.set_xscale('symlog',linthresh=100000); ax.set_xlabel('Training decisions (symlog)')
        ax.set_xlim(left=0); ax.set_title(title); ax.grid(alpha=.2)
    axes[0].set_ylim(0,1.02); axes[1].set_ylim(0,1.02)
    axes[-1].legend(fontsize=8)
    fig.suptitle('Fixed-map proxy: sampled-policy evaluation, 1,024 episodes per checkpoint')
    fig.tight_layout(); fig.savefig(output/'learning-curve.svg'); fig.savefig(output/'learning-curve.png',dpi=160)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('run',type=pathlib.Path)
    ap.add_argument('--output',type=pathlib.Path,required=True)
    ap.add_argument('--test-seed',type=int,default=1200000)
    ap.add_argument('--episodes',type=int,default=2048)
    args=ap.parse_args()
    torch.set_num_threads(1)
    args.output.mkdir(parents=True,exist_ok=False)
    config=json.loads((args.run/'config.json').read_text())
    shutil.copy2(args.run/'config.json',args.output/'config.json')
    shutil.copy2(args.run/'baselines.jsonl',args.output/'baselines.jsonl')
    env=Env(args.episodes,config['enemies'],seed=args.test_seed)
    test={'eval_seed':args.test_seed,'episodes_per_policy':args.episodes,'baselines':{},'seeds':[]}
    for mode in ('wait','random','pursuit'):
        test['baselines'][mode]=evaluate(env,mode=mode,seed=args.test_seed)
    curves=[]
    for folder in sorted(args.run.glob('seed-*')):
        curve=[json.loads(s) for s in (folder/'curve.jsonl').read_text().splitlines()]
        shutil.copy2(folder/'curve.jsonl',args.output/f'{folder.name}-curve.jsonl')
        curves.append(curve)
        last=curve[-1]
        checkpoint=folder/f"policy-{last['decisions']}.pt"
        saved=torch.load(checkpoint,map_location='cuda',weights_only=False)
        policy=Policy().cuda(); policy.load_state_dict(saved['model'])
        result={'seed':last['seed'],'decisions':last['decisions'],
                'greedy':evaluate(env,policy,'greedy',args.test_seed),
                'sampled':evaluate(env,policy,'sampled',args.test_seed)}
        test['seeds'].append(result)
        print(json.dumps(result),flush=True)
    (args.output/'fresh-test.json').write_text(json.dumps(test,indent=2)+'\n')
    baselines=[json.loads(s) for s in (args.run/'baselines.jsonl').read_text().splitlines()]
    plot_curves(curves,baselines,args.output)
    summary={'checkpoints':[],'fresh_test':test}
    for rows in zip(*curves):
        summary['checkpoints'].append({'decisions':rows[0]['decisions'],
            'clear_sampled':[r['sampled']['clear_rate'] for r in rows],
            'clear_greedy':[r['greedy']['clear_rate'] for r in rows],
            'train_seconds':[r['train_seconds'] for r in rows],
            'updates':rows[0]['updates'],
            'collection_seconds':[r['collection_seconds'] for r in rows],
            'update_seconds':[r['update_seconds'] for r in rows]})
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')

if __name__=='__main__': main()
