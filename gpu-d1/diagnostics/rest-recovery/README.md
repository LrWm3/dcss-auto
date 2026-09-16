# Sleeping-enemy recovery probes

Evaluated the existing 10,027,008-decision seed-0 wait-only and rest-to-full checkpoints, with no training or policy updates. Both use the 2048-decision deadline. The rest action is unavailable while any enemy is visible, including sleeping enemies, and at full HP. Policies have no explicit asleep/awake observation.

## Design

A 21×21 open room, player at center, one remaining required enemy, all others marked dead. Initial time is zero, and only the normal initial view is revealed. The enemy starts asleep. Native combat, regeneration, LOS, wake checks, and rest interruption are unchanged. Killing this enemy ends the episode.

- **Off-axis, wake range + 1:** enemy offset (7,1), visible and one Chebyshev tile beyond the six-tile wake radius.
- **Straight vision edge:** offset (7,0), also visible and one tile beyond wake range. These first two requests overlap in distance, so the test distinguishes their approach geometry.
- **Outside vision:** offset (8,0), hidden and rest initially legal below full HP.
- Player HP: **2/18, 9/18, 18/18**.
- Reference enemy: native kind 3, HP increased to 28, speed 10, damage 5.
- Hard enemy: native kind 4, HP increased to 48, speed 12, damage 5. These are deliberately tougher HP proxies than ordinary training enemies, not ogres.
- All eight rotations/reflections, 128 combat RNG seeds per orientation: **1,024 rollouts per table cell**. The RNG seeds repeat across orientations and conditions; these are not 1,024 independent combat seeds. No claims about variation across training seeds.
- Primary evaluation samples policy actions. Greedy evaluation is reported separately.

Controls know the enemy's location: `engage_now` walks directly toward it and keeps attacking; `heal_first` uses ordinary waits until full HP, then follows the same attack script. Learned policies receive only their normal observations, with no hidden-enemy information. Native setup assertions verify visibility, sleep, rest legality, absence of hidden monster records, zero initial decision time, and no invalid rest selections. Every rollout must terminate at the native deadline or earlier.

## Survival: sampled policies

Survival here means killing the enemy before dying. Every evaluated rollout ended in a clear or death; there were no timeouts. Each pair below is **wait-only / rest-enabled** clear percentage.

| Initial enemy position | Player HP | Reference enemy | Hard enemy |
|---|---:|---:|---:|
| Visible, off-axis | 2/18 | 88.7% / 84.5% | 36.8% / 27.2% |
| Visible, off-axis | 9/18 | 98.9% / 97.1% | 81.1% / 67.4% |
| Visible, off-axis | 18/18 | 99.3% / 97.9% | 91.9% / 88.3% |
| Visible, straight edge | 2/18 | 88.5% / 86.5% | 41.4% / 26.9% |
| Visible, straight edge | 9/18 | 98.9% / 98.3% | 83.5% / 69.1% |
| Visible, straight edge | 18/18 | 99.1% / 98.3% | 91.6% / 88.1% |
| Outside vision | 2/18 | 89.7% / 93.5% | 50.2% / 68.3% |
| Outside vision | 9/18 | 97.9% / 99.2% | 83.9% / 83.1% |
| Outside vision | 18/18 | 99.1% / 98.5% | 93.1% / 85.9% |

## Recovery behavior

The table averages the two enemy profiles equally. Rest use means at least one macro **before the enemy wakes**, including moving out of sight and then resting. Wake HP is measured immediately after the first waking transition; it can include that turn's regeneration/damage. Full-HP starts cannot select rest by design.

| Initial enemy position | Starting HP | Rest model: rested before wake | Wait model: mean wake HP | Rest model: mean wake HP |
|---|---:|---:|---:|---:|
| Visible, off-axis | 2/18 | 3.0% | 2.3 | 2.5 |
| Visible, off-axis | 9/18 | 1.9% | 9.2 | 9.2 |
| Visible, off-axis | 18/18 | 0.0% | 18.0 | 18.0 |
| Visible, straight edge | 2/18 | 3.4% | 2.4 | 2.5 |
| Visible, straight edge | 9/18 | 3.8% | 9.4 | 9.3 |
| Visible, straight edge | 18/18 | 0.0% | 18.0 | 18.0 |
| Outside vision | 2/18 | 70.5% | 4.1 | 13.3 |
| Outside vision | 9/18 | 92.9% | 11.0 | 17.4 |
| Outside vision | 18/18 | 0.0% | 18.0 | 18.0 |

Neither policy selected any ordinary waits while the enemy was asleep in the low- or half-HP sampled tests. There was one such wait per model in the full-HP visible cases across all their rollouts. This does not mean the models never heal: moving and fighting also regenerate HP.

Outside vision, the rest model's initial probability of selecting rest is **41.2% at 2 HP versus 86.9% at 9 HP**. This is the same for both enemy profiles because the enemy is hidden. By the time the monster wakes, it has rested in about 70% of low-HP episodes and 93% of half-HP episodes. It therefore responds to HP, but has not learned a consistently stronger preference for recovery as health becomes more critical.

When the enemy is already visible, the macro is masked. The rest model occasionally moves out of sight and rests (roughly 3–7% against the reference enemy, at most 1% against the harder enemy), but usually wakes it while still close to starting HP. It has not reliably learned either ordinary waiting to heal or creating a safe resting opportunity.

## Scripted controls: straight vision edge

| HP | Enemy | Engage immediately | Wait to full, then engage |
|---|---|---:|---:|
| 2/18 | reference | 37.5% | 100.0% |
| 2/18 | hard | 9.4% | 96.9% |
| 9/18 | reference | 93.8% | 100.0% |
| 9/18 | hard | 63.3% | 96.9% |
| 18/18 | reference | 100.0% | 100.0% |
| 18/18 | hard | 96.9% | 96.9% |

These controls establish a real recovery opportunity: the hard enemy can kill a full-health player, but engaging while critically injured is much worse. They are not optimal combat policies. Learned policies can exceed immediate-attack survival through movement and the regeneration it permits.

## Greedy sensitivity

Greedy rest-model performance is much worse than sampled performance, even at full health. This is a separate combat/action-selection weakness and prevents treating successful resting as sufficient for a successful encounter.

| Straight visible edge | Enemy | Wait greedy | Rest greedy |
|---|---|---:|---:|
| 2/18 | reference | 82.8% | 41.2% |
| 2/18 | hard | 35.5% | 12.5% |
| 9/18 | reference | 91.0% | 44.9% |
| 9/18 | hard | 75.4% | 30.5% |
| 18/18 | reference | 93.6% | 37.7% |
| 18/18 | hard | 86.7% | 42.0% |

## Interpretation and limits

The macro makes recovery behavior accessible when already legal. It has not produced a general “get healthy before a dangerous fight” policy. In particular, visible sleeping enemies still expose the missing preparation behavior. Outside-vision low-HP survival improves with the rest model, but it performs worse in several other cases. These are independently trained policies, so their survival differences do not isolate the causal effect of pressing rest; their combat strategies differ too.

This is a diagnostic suite on an artificial room with unusually durable enemies, one training seed, and fresh episode clocks. It does not replace ordinary held-out floor validation or establish generalization across trained seeds. Greedy and sampled outcomes are deliberately kept separate. Rotations/reflections share combat seeds, and native directional ties can affect trajectories.

## Reproduction

```sh
gpu-d1/.venv/bin/python gpu-d1/diagnostics/rest-recovery/run.py --reps 128 --greedy
python3 gpu-d1/diagnostics/rest-recovery/report.py
```

Checkpoints: `gpu-d1/learning-runs/vision15-rest-full/runs/{wait,rest}-seed0/snapshots/000010027008.pt`. The program rebuilds its native diagnostic library and generates its map under ignored `learning-runs/rest-recovery-probe/`. It writes six compact JSON reports under `gpu-d1/results/rest-recovery-*.json`; no new checkpoints are created. Each JSON includes per-condition behavior, survival, turns, decisions, and evaluation seconds (excluding map compilation and library build).
