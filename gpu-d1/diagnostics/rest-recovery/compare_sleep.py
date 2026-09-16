"""Compare the fresh sleep-feature rerun with the original 10M checkpoints."""
import json,pathlib
ROOT=pathlib.Path(__file__).resolve().parents[2]
lines=['# Visible sleep-status rerun: results','',
 'Fresh seed-0 wait-only and rest-enabled models, 10M decisions each. All settings match the previous rest experiment except 40 visible-enemy sleep-status inputs. New input weights start at zero; original initial weights are preserved. One training seed per arm; this is an exploratory comparison, not a multi-seed significance test.','',
 '## Ordinary held-out floors','',
 '| Model | Sleep input | Clear | Death | Timeout | Training seconds |','|---|---|---:|---:|---:|---:|']
for suffix,feature in [('rest-full',False),('rest-sleep',True)]:
    d=json.loads((ROOT/f'results/{suffix}-training-summary.json').read_text())
    for job in d['jobs']:
        m=job['final']['sampled']
        lines.append(f"| {job['job']['name']} | {feature} | {100*m['clear_rate']:.1f}% | {100*m['death_rate']:.1f}% | {100*m['timeout_rate']:.1f}% | {job['train_seconds']:.1f} |")
for mode in ['sampled','greedy']:
    lines += ['',f'## Recovery probes: {mode}', '',
      'Each cell has 128 combat seeds × eight orientations. Combat seeds repeat across orientations. Sleep is visible only inside LOS. Rest remains masked by any visible enemy. Percentages below describe policy behavior and survival, not training-seed uncertainty.','',
      '| Position | HP | Enemy | Model | Sleep input | Clear | Waited while asleep | Rested before wake | Mean HP at wake |',
      '|---|---:|---|---|---|---:|---:|---:|---:|']
    for arm in ['wait','rest']:
        for prefix,feature in [('rest-recovery',False),('rest-sleep-recovery',True)]:
            d=json.loads((ROOT/f'results/{prefix}-{arm}-{mode}.json').read_text())
            for r in d['conditions']:
                lines.append(f"| {r['geometry']} | {r['hp']} | {r['difficulty']} | {arm} | {feature} | {100*r['clear']:.1f}% | {100*r['ever_waited_asleep']:.1f}% | {100*r['rested_before_wake']:.1f}% | {r['wake_hp']:.2f} |")
(ROOT/'results/rest-sleep-comparison.md').write_text('\n'.join(lines)+'\n')
