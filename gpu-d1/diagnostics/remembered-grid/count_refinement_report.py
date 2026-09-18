"""Render count-refinement results without changing the original screen."""
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent
RESULTS=HERE.parents[1]/'results'
def main():
    rows=[]
    for kind in ['counts','counts2','count_edges']:
        q=json.loads((RESULTS/f'remembered-grid-compact-{kind}.json').read_text())
        b=json.loads((RESULTS/f'remembered-grid-compact-{kind}-performance.json').read_text())
        t=q['provenance']['training'][-1]
        rows.append(dict(kind=kind,selected_update=q['provenance']['selected_update'],training_seconds=t['training_seconds'],collected_decisions=t['decisions'],main=q['test_greedy']['summary'],long=q['long_greedy']['summary'],sampled=q['test_sampled']['summary'],paired=q['paired']['both_in_pair_correct'],paired_erased=q['paired_erased']['both_in_pair_correct'],network_decisions_per_second=b['rows'][1]['network_only_four_epoch_decisions_per_second']['1'],amp=b['amp_test']['summary']))
    (RESULTS/'remembered-grid-count-refinements-summary.json').write_text(json.dumps(dict(scope='One seed; synthetic 32x32 navigation, supervised plus learner-state demonstrations. Network-only PPO cost on 80x70, not a PPO learning run.',rows=rows),indent=2)+'\n')
    lines=['## Measured results','', '| Summary | Known stairs | Exploration | Long known stairs | Long exploration |','|---|---:|---:|---:|---:|']
    for r in rows:
        lines.append(f"| {r['kind']} | {r['main']['known_stairs']['exit']:.2%} | {r['main']['exploration']['exit']:.2%} | {r['long']['known_stairs']['exit']:.2%} | {r['long']['exploration']['exit']:.2%} |")
    lines+=['','Greedy held-out exits. Main tasks have 256 episodes each; long tasks have 128 each. Original 4x4 counts are reused from the previous screen. One training seed does not measure seed variability.','','| Summary | Training seconds | Selected update | Goal pairs correct | Network-only PPO decisions/s |','|---|---:|---:|---:|---:|']
    for r in rows:
        lines.append(f"| {r['kind']} | {r['training_seconds']:.1f} | {r['selected_update']:,} | {r['paired']}/24 | {r['network_decisions_per_second']:,.0f} |")
    lines+=['','Training time excludes validation. Each arm receives 3,072,000 supervised examples; learner-state collection differs. Network estimates use precomputed deterministic summaries, AMP, batch 1024 and four optimizer passes, with every learned parameter trainable. They exclude environment, rollout, GAE and buffer overhead. Quality uses fresh summaries; no stale-cache quality is assumed.','','[Raw summary](../../results/remembered-grid-count-refinements-summary.json).','']
    p=HERE/'COUNT-REFINEMENTS.md';s=p.read_text();marker='<!-- measured-results -->';s=s.split(marker)[0].rstrip();p.write_text(s+'\n\n'+marker+'\n'+'\n'.join(lines))
    print(json.dumps(rows,indent=2))
if __name__=='__main__':main()
