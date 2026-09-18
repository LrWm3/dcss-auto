"""Summarize matched-resolution visited-history training comparisons."""
import argparse,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
RESULTS=HERE.parents[1]/'results'
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--bits',action='store_true');args=ap.parse_args()
    kinds=['counts2','counts2_visits','counts2_visit_bits'] if args.bits else ['counts','counts_visits','counts2','counts2_visits']
    comparisons=[('counts2','counts2_visit_bits'),('counts2_visits','counts2_visit_bits')] if args.bits else [('counts','counts_visits'),('counts2','counts2_visits')]
    stem='visit-bits' if args.bits else 'visit-counts';doc='VISIT-BITS.md' if args.bits else 'VISIT-COUNTS.md'
    rows=[]
    for kind in kinds:
        q=json.loads((RESULTS/f'remembered-grid-compact-{kind}.json').read_text())
        b=json.loads((RESULTS/f'remembered-grid-compact-{kind}-performance.json').read_text())
        t=q['provenance']['training'][-1]
        rows.append(dict(kind=kind,selected_update=q['provenance']['selected_update'],training_seconds=t['training_seconds'],collected_decisions=t['decisions'],supervised_examples=t['supervised_examples'],main=q['test_greedy']['summary'],long=q['long_greedy']['summary'],sampled=q['test_sampled']['summary'],paired=q['paired']['both_in_pair_correct'],paired_erased=q['paired_erased']['both_in_pair_correct'],network_decisions_per_second=b['rows'][1]['network_only_four_epoch_decisions_per_second']['1'],amp=b['amp_test']['summary'],other_gpu_processes=b['other_gpu_processes_at_end']))
    # Paired episode counts help identify whether added visits rescue the same failures.
    paired={}
    for base,new in comparisons:
        a=json.loads((RESULTS/f'remembered-grid-compact-{base}.json').read_text())
        b=json.loads((RESULTS/f'remembered-grid-compact-{new}.json').read_text())
        pair={}
        for split in ['test_greedy','long_greedy']:
            aa=a[split]['rows'];bb=b[split]['rows'];assert len(aa)==len(bb)
            for x,y in zip(aa,bb):assert (x['scenario'],x['map'],x['kind'])==(y['scenario'],y['map'],y['kind'])
            pair[split]={name:{'rescued':sum(x['exit']==0 and y['exit']==1 for x,y in zip(aa,bb) if x['kind']==k),'lost':sum(x['exit']==1 and y['exit']==0 for x,y in zip(aa,bb) if x['kind']==k)} for k,name in enumerate(['known_stairs','exploration','threat_backtrack'])}
        paired[base+' -> '+new]=pair
    summary=dict(scope='One training seed per arm; equal supervised budget, synthetic 32x32 navigation. Reuses previous no-global-visit arms. Network-only PPO estimates at 80x70, no PPO learning.',rows=rows,paired_episode_outcomes=paired)
    (RESULTS/f'remembered-grid-{stem}-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    lines=['## Results','', '| Global summary | Known stairs | Exploration | Long known stairs | Long exploration |','|---|---:|---:|---:|---:|']
    for r in rows:lines.append(f"| {r['kind']} | {r['main']['known_stairs']['exit']:.2%} | {r['main']['exploration']['exit']:.2%} | {r['long']['known_stairs']['exit']:.2%} | {r['long']['exploration']['exit']:.2%} |")
    lines+=['','Greedy held-out exit rates. One seed does not establish robustness across training seeds.','','| Global summary | Sampled known stairs | Sampled exploration | Main threat backtrack | Long threat backtrack |','|---|---:|---:|---:|---:|']
    for r in rows:lines.append(f"| {r['kind']} | {r['sampled']['known_stairs']['exit']:.2%} | {r['sampled']['exploration']['exit']:.2%} | {r['main']['threat_backtrack']['exit']:.2%} | {r['long']['threat_backtrack']['exit']:.2%} |")
    lines+=['','| Global summary | Training seconds | Selected update | Goal pairs | Network-only PPO decisions/s |','|---|---:|---:|---:|---:|']
    for r in rows:lines.append(f"| {r['kind']} | {r['training_seconds']:.1f} | {r['selected_update']:,} | {r['paired']}/24 | {r['network_decisions_per_second']:,.0f} |")
    lines+=['','Training seconds exclude validation. Throughput uses precomputed deterministic summaries, with all learned parameters trainable, AMP and four optimizer passes at batch 1024. It assumes preprocessing once per decision, excludes end-to-end PPO overhead, and was measured with no competing GPU jobs.','',f'[Machine-readable summary and paired episode counts](../../results/remembered-grid-{stem}-summary.json).','']
    p=HERE/doc;s=p.read_text();marker='<!-- measured-results -->';p.write_text(s.split(marker)[0].rstrip()+'\n\n'+marker+'\n'+'\n'.join(lines))
    print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
