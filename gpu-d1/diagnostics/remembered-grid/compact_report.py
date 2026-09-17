"""Render the completed representation screen from checked result artifacts."""
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent
RESULTS=HERE.parents[1]/'results'

def main():
    rows=[]
    for kind in ['attn','coarse','counts']:
        q=json.loads((RESULTS/f'remembered-grid-compact-{kind}.json').read_text());b=json.loads((RESULTS/f'remembered-grid-compact-{kind}-performance.json').read_text());t=q['provenance']['training'][-1]
        rows.append(dict(kind=kind,selected_update=q['provenance']['selected_update'],training_seconds=t['training_seconds'],collected_decisions=t['decisions'],supervised_examples=t['supervised_examples'],main={k:v['exit'] for k,v in q['test_greedy']['summary'].items()},long={k:v['exit'] for k,v in q['long_greedy']['summary'].items()},sampled={k:v['exit'] for k,v in q['test_sampled']['summary'].items()},paired=q['paired']['both_in_pair_correct'],paired_erased=q['paired_erased']['both_in_pair_correct'],amp={k:v['exit'] for k,v in b['amp_test']['summary'].items()},compute=b['rows'],encoder_ms=b['encoder_ms'],reader_ms=b['reader_ms'],cache_bytes=b['map_cache_bytes_per_world'],parameters=b['parameters'],other_gpu_processes=b['other_gpu_processes_at_end']))
    summary=dict(scope='One-seed equal-supervised-budget synthetic navigation representation screen. No PPO learning runs. Network benchmark is 80x70, quality is 32x32.',rows=rows)
    (RESULTS/'remembered-grid-compact-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    lines=['## Results','', '| Representation | Known stairs | Exploration | Longer known stairs | Longer exploration | Goal pairs |','|---|---:|---:|---:|---:|---:|','| Original spatial | 92.19% | 90.23% | 53.91% | 67.19% | 24/24 |','| Previous cached reader, fresh terrain | 69.14% | 91.41% | 32.03% | 63.28% | 24/24 |']
    for r in rows:lines.append(f"| {r['kind']} | {r['main']['known_stairs']:.2%} | {r['main']['exploration']:.2%} | {r['long']['known_stairs']:.2%} | {r['long']['exploration']:.2%} | {r['paired']}/24 |")
    lines+=['','Greedy exits on the same regression splits. Main known/exploration each contain 256 episodes; long each contain 128. Paired-goal erasure results and sampled/AMP outcomes are in the summary JSON. The earlier cached paired-goal result used interval 4; the statistic measures the first action after cache initialization, so refresh interval does not alter that readout.','','| Representation | Training seconds (excludes validation) | Collected decisions | Selected update |','|---|---:|---:|---:|']
    for r in rows:lines.append(f"| {r['kind']} | {r['training_seconds']:.1f} | {r['collected_decisions']:,} | {r['selected_update']:,} |")
    lines+=['','All arms used 3,072,000 sampled supervised examples. Collected decisions differ because learner trajectories differ.','','| Full-map network-only PPO estimate | Trainable encoder, refresh every decision | Frozen encoder, refresh every decision | Frozen encoder, one refresh per 4 decisions |','|---|---:|---:|---:|']
    for r in rows:
        train,frozen=r['compute'];lines.append(f"| {r['kind']} | {train['network_only_four_epoch_decisions_per_second']['1']:,.0f}/s | {frozen['network_only_four_epoch_decisions_per_second']['1']:,.0f}/s | {frozen['network_only_four_epoch_decisions_per_second']['4']:,.0f}/s |")
    lines+=['','Previous optimized spatial reference: 4,370/s with a trainable encoder, AMP and compilation, batch 1024. New models use AMP without compilation, the same training batch size, and the same four-pass cost formula. Freezing changes what can learn. The count encoder has no trainable parameters: its precomputed-input ("frozen") column still trains every learned parameter, merely skipping deterministic count pooling on each replay presentation. None of these numbers include simulator or rollout overhead. Quality at stale refresh intervals has not been measured in this screen.','','[Machine-readable summary](../../results/remembered-grid-compact-summary.json).','']
    p=HERE/'COMPACT.md';text=p.read_text();heading='# Position-aware compact map representations\n'
    start='<!-- compact-results:start -->';end='<!-- compact-results:end -->'
    block=start+'\n'+'\n'.join(lines)+end+'\n\n'
    if start in text:
        a=text.index(start);b=text.index(end,a)+len(end);text=text[:a]+block.rstrip()+text[b:]
    elif '## Results\n' in text:
        a=text.index('## Results\n');b=text.index('This screen compares',a);text=text[:a]+block+text[b:]
    else:text=text.replace(heading,heading+'\n'+block,1)
    p.write_text(text)
    print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
