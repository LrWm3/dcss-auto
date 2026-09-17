"""Turn frozen results into a concise, auditable experiment report."""
import json
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]

def main():
    r=json.loads((ROOT/'results/remembered-grid.json').read_text());lines=['# Remembered-grid navigation: completed first demonstration','',
    'A learned local/global spatial encoder can navigate these unfamiliar synthetic floors without frontier arrows, stair arrows, route distances, or runtime controller actions. This is a supervised navigation result, not an ordinary-D1 or PPO result.','',
    'All arms trained for 12,000 optimizer updates (3,072,000 sampled supervised examples). Spatial-model checkpoints were selected using validation; the simple CNN uses its final checkpoint. Training used behavior cloning plus corrective labels on mixed student/teacher trajectories. The policy starts from scratch.','',
    '## Main held-out results','',
    'Greedy exit percentages. Known stairs and exploration each contain 256 episodes on the same 64 held-out mazes (four placements per map). Pressure contains 32 separately generated junctions. The budget is 256 physical turns including setup history.','',
    '| Representation | Known stairs | Explore to stairs | Threat backtracking |','|---|---:|---:|---:|']
    names={'memory':'Local + simple global CNN','local-spatial':'Local crop only','terrain-spatial':'Local + spatial global terrain','memory-spatial':'Local + spatial global terrain + enemy memory'}
    for key in ['local-spatial','memory','terrain-spatial','memory-spatial']:
        s=r['arms'][key]['evaluations']['test_greedy']['summary'];lines.append('| '+names[key]+' | '+' | '.join(f"{100*s[k]['exit']:.2f}%" for k in ['known_stairs','exploration','threat_backtrack'])+' |')
    main=r['arms']['memory-spatial'];s=main['evaluations']['test_sampled']['summary'];lines+=['',f"With sampled actions, the full spatial policy exits in **{s['known_stairs']['exit']*100:.2f}%** of known-stair cases and **{s['exploration']['exit']*100:.2f}%** of exploration cases. The untrained spatial policy exited in none of the validation episodes.",'',
    'The pressure suite is too easy to establish the value of last-seen-enemy memory: the local-only and terrain-only controls also solve it. Success in those fixtures must not be interpreted as proof that the policy remembered and reasoned about the monster. All pressure exits should be read alongside the recorded wake/kill statistics.','',
    '## Paired distant-goal diagnostic','',
    'The local crop, player statistics, action mask and walked path are identical within each pair. Only the distant remembered staircase locations differ. Both possible exits are outside the local crop. Initial direction, rather than eventual exit, tests whether the policy uses that global information.','',
    '| Representation | Correct initial direction | Both members correct |','|---|---:|---:|']
    for key in ['local-spatial','memory','terrain-spatial','memory-spatial']:
        q=r['arms'][key]['goal_probe'];lines.append(f"| {names[key]} | {100*q['initial_correct']:.2f}% | {q['both_in_pair_correct']} / {q['pairs']} |")
    q=main['goal_probe_without_global'];lines+=['',f"Zeroing the trained full policy's global features gives {100*q['initial_correct']:.2f}% correct initial directions and {q['both_in_pair_correct']}/24 complete pairs. This is an out-of-distribution intervention; the separately trained local-only control is the cleaner comparison.",'',
    '## Larger/longer layouts','',
    'These use 6x6 maze construction nodes rather than the 4x4/5x5 training layouts, with 128 episodes per navigation condition on 32 maps. Pressure backtracks are 12/14 tiles rather than 4/6/8/10. The deadline is increased to 512 turns so the history walk plus return is feasible; this is not a matched-deadline comparison.','',
    '| Representation | Known stairs, greedy | Exploration, greedy | Known stairs, sampled | Exploration, sampled |','|---|---:|---:|---:|---:|']
    for key in ['local-spatial','memory','terrain-spatial','memory-spatial']:
        e=r['arms'][key]['evaluations'];vals=[e[mode]['summary'][task]['exit'] for mode in ['long_greedy','long_sampled'] for task in ['known_stairs','exploration']];lines.append('| '+names[key]+' | '+' | '.join(f'{100*v:.2f}%' for v in vals)+' |')
    lines+=['','The observation-limited teacher reaches every exit in the recorded validation, test, and long panels. Remaining model failures therefore have a demonstrated feasible route under the same budget. This does not show that every arbitrary Crawl floor is solvable.','',
    '## Training cost','',
    '| Representation | Rollout decisions | Measured training/collection time | Selected update | Parameters |','|---|---:|---:|---:|---:|']
    for key in ['local-spatial','memory','terrain-spatial','memory-spatial']:
        a=r['arms'][key];h=a['training'][-1];lines.append(f"| {names[key]} | {h['decisions']:,} | {h['training_seconds']:.1f} s | {a['checkpoint_step']:,} | {a['parameters']:,} |")
    lines+=['','Times include teacher-label generation and optimizer work, and exclude validation rollouts. The initial CNN/U-net measurements also include validation environment-construction overhead, fixed in subsequent control runs. Compilation, fixture generation, final evaluation and implementation time are additional. Rollout decisions exclude scripted reset histories and are not autonomous PPO decisions.','',
    '## Interpretation and limits','',
    '- This establishes useful map-conditioned navigation on unseen layouts within these procedural families. The stronger spatial encoder outperforms simply flattening a coarse global CNN summary.',
    '- The distant-goal pairs distinguish using global information from a fixed local movement habit. Consult the measured table rather than assuming every policy passes.',
    '- Longer-route performance measures a real remaining generalization limit; the representation is not a guaranteed pathfinding algorithm.',
    '- One training seed, fixed player stats, at most one dangerous sleeper, small synthetic floors. No ordinary-floor combat retention, full 80x70 Crawl map generalization, or PPO improvement is claimed.',
    '- Enemy-memory benefits remain unproven by this easy pressure suite. It needs situations where histories require different useful decisions, rather than a universally safe backtracking response.','',
    '## Checks and artifacts','',
    f"- {r['semantics']['distinct_layouts']} distinct terrain arrays across the four splits; {r['semantics']['cpu_cuda_transitions']} CPU/CUDA transition comparisons; {r['semantics']['hidden_state_checks']} hidden-state/terrain checks; {r['semantics']['out_of_view_memory_pairs']} out-of-view memory pairs.",
    '- The original automatic-reset behavior and legacy semantic checks pass without the experiment-only compile flag.',
    '- [Exact measurements](../../results/remembered-grid.json), [illustrative trajectories](../../results/remembered-grid-examples.svg), [implementation and reproduction](README.md).',
    '- Raw models/maps remain in the ignored, bounded `learning-runs/remembered-grid` directory. Original experiments and unrelated result files are untouched.','']
    (HERE/'RESULTS.md').write_text('\n'.join(lines))
    print('\n'.join(lines[:18]))
if __name__=='__main__':main()
