"""Render the completed symbolic sequence screen with its protocol caveats."""
import json,hashlib
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];OUT=ROOT/'learning-runs/remembered-grid'
def main():
    rows=[]
    for kind in ['ff','gru']:
        r=json.loads((ROOT/f'results/remembered-grid-symbolic-{kind}.json').read_text());folder=OUT/f'symbolic-{kind}'
        rows.append(dict(kind=kind,main=r['test_greedy']['summary'],long=r['long_greedy']['summary'],sampled=r['test_sampled']['summary'],training=r['training'][-1],selected=r['selected']['step'],reset_memory=r.get('reset_memory_test',{}).get('summary'),manifest=json.loads((folder/'manifest.json').read_text()),checkpoint_sha256=hashlib.sha256((folder/'best.pt').read_bytes()).hexdigest()))
    summary=dict(scope='One-seed two-scale symbolic representation screen, supervised/DAgger sequence training, not PPO. Direct ff-vs-GRU comparison; older runs use different replay and architecture.',rows=rows)
    (ROOT/'results/remembered-grid-symbolic-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    lines=['## Results','', '| Model | Known stairs | Exploration | Long known stairs | Long exploration |','|---|---:|---:|---:|---:|']
    for r in rows:lines.append(f"| {r['kind']} | {r['main']['known_stairs']['exit']:.2%} | {r['main']['exploration']['exit']:.2%} | {r['long']['known_stairs']['exit']:.2%} | {r['long']['exploration']['exit']:.2%} |")
    lines+=['','Greedy held-out exits: 256 episodes each main task, 128 each long task.','','| Model | Sampled known stairs | Sampled exploration | Main threat backtrack | Long threat backtrack |','|---|---:|---:|---:|---:|']
    for r in rows:lines.append(f"| {r['kind']} | {r['sampled']['known_stairs']['exit']:.2%} | {r['sampled']['exploration']['exit']:.2%} | {r['main']['threat_backtrack']['exit']:.2%} | {r['long']['threat_backtrack']['exit']:.2%} |")
    lines+=['','| Model | Training seconds | Valid supervised examples | Collected decisions | Selected update |','|---|---:|---:|---:|---:|']
    for r in rows:
        t=r['training'];lines.append(f"| {r['kind']} | {t['training_seconds']:.1f} | {t['supervised_examples']:,} | {t['decisions']:,} | {r['selected']:,} |")
    lines+=['','Training time includes collection and optimization, excludes validation. Different valid-example counts result from terminal padding and policy-dependent trajectories; both arms receive 12,000 optimizer updates.','']
    r=rows[1]['reset_memory'];lines+=['Resetting GRU state before every evaluation action gives '+', '.join(f"{k}: {v['exit']:.2%}" for k,v in r.items())+'. This post-training intervention measures reliance, not the performance of a retrained memoryless model.','','[Raw summary and provenance](../../results/remembered-grid-symbolic-summary.json).','']
    p=HERE/'SYMBOLIC.md';s=p.read_text();marker='<!-- measured-results -->';p.write_text(s.split(marker)[0].rstrip()+'\n\n'+marker+'\n'+'\n'.join(lines))
    print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
