# Controlled ring generalization experiment

Status: first pass completed; see [the 10M results](LEARNING-RING-GENERALIZATION-10M.md).

Question: at the same decision budget, does training the corrected ring policy
on varied layouts improve performance on unseen layouts, and is any failure
already visible on its training layouts?

## First pass

Use the recent 40-enemy, 1024-turn ring task as the base. Fix the player-feature
offset collision in both arms. Port its existing dynamics and observations to
multi-map loading without adopting v2's different combat or observation rules.

| Setting | A: single-map reference | B: varied maps |
| --- | --- | --- |
| Training layouts | Original fixed map | All 256 training maps, uniformly sampled per reset |
| Decisions | 10,027,008 | 10,027,008 |
| Training seed | 0 | 0 |
| Enemies / deadline | 40 / 1024 | 40 / 1024 |
| Observation | Corrected 11x11 remembered-terrain ring | Same |
| First-seen floor reward | 0.002 per new floor cell in 9x9 view | Same |
| Sleep, combat, stats, network, PPO | Existing ring settings | Same |

Preserve the original global enemy-position features in both arms. Therefore
this is generalization in the existing toy task, not a hidden-enemy exploration
test. Do not also change stat distributions, add frontier input, rescale the
clock, alter rewards, or increase network size. Freeze the original player and
monster configuration rather than importing per-map character stats.

This is 20M decisions total. Equal decisions intentionally measure performance
at a fixed compute budget; they do not equalize experience per layout. Repeat
with seeds 1 and 2 before treating a difference as reliable. A weak 10M result
does not rule out later learning.

The seed-0 implementation pass used 10M decisions per arm. The multi-map arm
had 0% validation clears and the single-map arm had 30.4% on its original map
but 0% on validation. This is currently a learning-capacity result, not a
generalization result, because the multi-map policy was also weak on its
training-map panel.

## Implementation checks before training

- Derive the player offset from `162 + 5 * ENEMIES`. Verify all 40 monster
  slots and all four player features separately, including dead monsters.
- On the original map, run identical prescribed actions in old and ported
  environments: transitions, rewards, masks, sleep, and memory must match;
  only the documented player/monster feature correction may differ. CPU/GPU
  parity alone would not detect a shared observation bug.
- Exercise every map ID directly and compare its floor/index/distance tables
  with the standalone map file, including the largest offsets. Check resets
  clear ring history and choose valid, connected spawn cells.
- Verify unknown ring cells remain zero independent of hidden terrain, known
  walls are -1, known floors +1, initial visibility is unrewarded, and only
  newly revealed floor in the 9x9 window earns the exploration reward.
- Save resolved settings, map manifests, observation schema, source/header
  hashes, and built-library hash with each run.

## Evaluation

Checkpoints: initialization, 1M, 3M, and 10M decisions (rounded to whole
rollouts). Evaluate both arms on exactly the same fixed episode specifications:

- Original map: 1,024 fresh episodes, to measure single-map task learning.
- A preselected, geometry-diverse panel of 32 training maps: 64 episodes per
  map, to measure B's performance on familiar layouts. These are not all
  familiar layouts for A, so label this panel accordingly.
- All 32 validation maps: 64 episodes per map, to compare unseen-layout play.

Preselect panels and initial states before inspecting scores. Report per-map
results and the equally weighted map mean. Use sampled actions as the primary
policy, greedy as secondary. Repeat the final evaluation with a fresh episode
bank. Keep the 100-map test split for the final selected setup.

Primary outcome: validation clear rate. Also record kills/40, deaths, timeouts,
revealed-floor fraction, steps on distinct floor cells, movement/wait/attack
counts, and enemies left asleep at timeout. Report raw task outcomes separately
from exploration-shaped return. Stratify validation results by map size to
expose fixed-budget effects; do not adjust the deadline in this experiment.

Include random and full-map pursuit references, labeling pursuit's privileged
terrain knowledge. Compare A and B directly for the causal question. Quantify
uncertainty across validation maps and, after replication, across training
seeds; do not treat thousands of episodes as thousands of independent layouts.

## How to interpret the result

- A learns its map, but B is weak even on its training-map panel: diversity
  increases the learning burden at this budget. Try an intermediate map count
  or a longer budget as a separate experiment.
- B performs well on familiar maps but poorly on validation: evidence of a
  generalization gap; inspect per-map navigation and coverage failures.
- B beats A on the same validation maps with similar combat survival: evidence
  that varied-layout training helps under this fixed budget. Replicate seeds.
- Both arms remain weak on their familiar layouts: prioritize learning and
  navigation diagnostics before drawing generalization conclusions.

Defer the frontier comparison until this ring-only experiment is interpretable.
Its nearest-frontier distance currently uses the true map's distance fields;
audit that information access explicitly before calling it a memory-only input.
