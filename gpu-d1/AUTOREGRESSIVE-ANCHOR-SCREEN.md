# Fixed-reference protection during PPO

Question: can a soft constraint preserve the imitated navigation representation
while allowing reinforcement learning to improve behavior? Lower learning rate
alone collapsed by 10M; freezing only the first layer preserved competence.

All jobs start from the same original imitation checkpoint. Original reward
(+1 clear, -0.00001 per physical turn), entropy zero, 24 enemies, 2048 physical
turns, training corpus/clumping, and PPO settings are unchanged. One initial
training seed; full 1024-episode validation at 0, 1M, 5M, and 10M decisions.

The fixed reference is the original imitation network, never the last PPO
checkpoint. Each auxiliary minibatch mixes 256 current observations and 256
reference-buffer observations. The buffer contains 65,536 observations collected
by the sampled imitation policy on training maps with a separate seed; it uses
no validation maps. Sampling uses checkpointed Torch RNG state.

- Feature weights 10 and 100: mean squared difference of first-layer tanh
  activations. Random D4 transforms cover orientations actually processed by the
  exact-D4 encoder. Later layers have no direct feature-loss constraint.
- Policy weights 0.01 and 0.1: exact KL(reference || current) over the 18 legal
  joint actions, including both action type and conditional direction.

The auxiliary term is added to PPO's loss, not the environment reward. It does
not run a teacher controller during validation. Every parameter remains trainable.
The original runner's default behavior is unchanged when anchoring is absent.

Preflight verifies zero reference loss at initialization, positive loss and
restoring gradient after a parameter perturbation, no gradients in the reference,
and feature-gradient isolation to the first layer. Each suite has a 3GiB disk
cap and 10GiB free-space reserve; the shared reference buffer is about 255MiB.

Success requires separating preservation (clear rates/navigation remain intact)
from improvement (better clear rate or efficiency without sacrificing survival).
Any promising single-seed result needs independent training-seed confirmation.

## Initial seed-0 screen (completed)

| Constraint | Sampled clears at 10M | Greedy clears at 10M | Sampled successful turns | Greedy successful turns | Training seconds |
|---|---:|---:|---:|---:|---:|
| feature10-seed0 | 81.74% | 0.00% | 1559.4 | n/a | 253.5 |
| feature100-seed0 | 97.17% | 24.12% | 781.6 | 1655.3 | 261.2 |
| policy001-seed0 | 95.51% | 63.28% | 880.5 | 1636.0 | 297.7 |
| policy01-seed0 | 96.48% | 93.95% | 685.0 | 681.4 | 299.1 |

Initial imitation: 96.88% sampled, 94.43% greedy, successful turns 680.3/680.8.
Feature anchoring at either tested strength does not protect greedy navigation.
Policy KL weight 0.01 also degrades. Policy KL weight 0.1 retains navigation and
clear rate through 10M with all layers trainable, but does not demonstrate an
improvement beyond imitation. Stronger policy KL and training-seed replications
are being checked separately. The screen took 1514.7 seconds including evaluation.

## Follow-ups

Policy KL weight 1, seed 0, also completed 10M: 97.17% sampled clears,
94.53% greedy clears, with 679.8/680.3 turns per successful episode. Training
cost 300.0 seconds. Weight 0.1 is being replicated with training seeds 1 and 2;
all start from the same imitation checkpoint, so these vary PPO randomness,
not imitation training.

An additional seed-0, 10M experiment uses policy KL weight 1 only when the
observation contains no visible awake enemy. It normalizes by eligible states,
leaves combat decisions unconstrained by imitation, and still permits all layers
to train. Signed sleep slots are audited from native code: -1 awake, +1 asleep,
0 nonvisible/dead/unused. Tests verify the absence of combat gradients and
correct treatment of sleeping and nonvisible enemies. The experiment uses the
same reward, simulator, PPO settings and reference buffer as the full-policy
constraint; no heuristic action override is introduced.

The final comparison was queued in advance on all 100 test maps, 16 placements
per map, seed 1930017, sampled and greedy. It includes original imitation, all
three weight-0.1 PPO seeds, weight 1, the frozen-first-layer control, and the
navigation-only variant. Paired clear/return differences use a map-cluster
bootstrap; common-success turn differences avoid comparing different success
subsets. These intervals quantify test-map uncertainty, not training-seed
uncertainty. Results are not used to choose among further hyperparameters.

A fixed training-observation probe also shows why parameter movement alone is
not a diagnosis. At 10M, weight-0.1 policy anchoring permits first-layer L2
parameter movement of 8.03 and feature MSE 0.170, while joint policy KL remains
0.0114. Feature weight 100 has much smaller feature MSE (0.0000255), but policy
KL 0.0893 and poor greedy navigation. These are 512 training-buffer observations,
not a universal bound. They support protecting behavior directly rather than
assuming small feature drift guarantees policy stability.

## Training-seed replication (completed)

| PPO seed | Sampled clear rate | Greedy clear rate | Successful sampled turns | Successful greedy turns |
|---|---:|---:|---:|---:|
| policy0.1-seed1 | 97.17% | 95.21% | 682.6 | 693.4 |
| policy0.1-seed2 | 96.48% | 94.14% | 683.2 | 682.4 |

Together with seed 0, weight 0.1 averages 96.71% sampled clears and 94.43%
greedy clears at 10M, compared with initial imitation 96.88%/94.43%. This is
reliable preservation across these three PPO seeds, not a demonstrated average
clear-rate improvement. Each additional 10M seed took about 300 seconds of
training; the two-run continuation of the screen took 794.0 seconds including
evaluation. The three policies share the same initial imitation checkpoint.

## Final test results and interpretation

All eight fresh training jobs completed 10M decisions. The independent test panel
used 100 layouts not used to select these settings, 16 placements per layout,
with identical initial scenarios and sampling seed for every policy. Each cell
below is an evaluation of 1,600 episodes; the weight-0.1 row averages three PPO
seeds on the same episode panel, not 4,800 distinct scenarios.

| Model at 10M (except imitation) | Sampled clears | Greedy clears | Sampled successful turns | Greedy successful turns |
|---|---:|---:|---:|---:|
| Initial imitation | 96.75% | 93.56% | 675.3 | 675.0 |
| Frozen first layer, seed 0 | 96.88% | 93.38% | 698.1 | 727.9 |
| Full-policy KL 0.1, three-seed mean | 96.27% | 93.54% | 679.3 | 680.2 |
| Full-policy KL 1, seed 0 | 96.63% | 93.63% | 677.9 | 673.5 |
| Navigation-only KL 1, seed 0 | 96.88% | 93.75% | 674.3 | 668.2 |

Full-policy KL 0.1 preserves competence across three training seeds, but does
not beat imitation on this test: sampled clear difference -0.48 percentage
points (map-bootstrap 95% interval -1.31 to +0.37), greedy -0.02 points (-0.94
to +0.94). Common-success episodes are slightly slower, by 3.46 sampled turns
(interval +0.92 to +5.89) and 4.65 greedy turns (+2.20 to +7.23). Absence of a
significant clear difference is not proof of equivalence or noninferiority.

The navigation-only variant is a small, exploratory efficiency result. Among
1,464 greedy episodes both policies clear, it saves 8.10 turns relative to
imitation (map-bootstrap 95% interval 5.56 to 10.58 turns saved). This is about
1.2% of a typical successful run. Sampled common-success improvement is only
1.78 turns, with interval -1.46 to +4.94 turns saved, so is not established.
Clear-rate gains are just 2/1,600 sampled and 3/1,600 greedy episodes; their
intervals include zero. Overall reward superiority is therefore not established.
This variant has one training seed; the interval reflects map variation only,
and the several screened settings make the efficiency finding exploratory.

On validation, navigation-only anchoring gave 96.29% sampled and 94.53% greedy
clears, with 672.7/672.9 successful turns. It reduced WAIT usage (sampled 57.2 to
42.0 actions per episode) while MOVE usage rose (368.3 to 373.8); sampled deaths
rose from 3.13% to 3.71%. These aggregate action counts describe the change,
not a causal proof that individual waits were unnecessary. Its penalty is
normalized over eligible noncombat states, so it is not an exactly matched
auxiliary-gradient-magnitude ablation of the full-policy loss.

Practical conclusion: continuous policy anchoring is a promising replacement
for hard first-layer freezing. It permits substantial encoder changes while
preserving behavior through 10M, and avoids the navigation slowdown seen with
the frozen-layer control. The strongest evidence is prevention of catastrophic
forgetting, not autonomous improvement beyond imitation. The navigation-only
variant offers a modest greedy-efficiency lead to replicate, not a demonstrated
clear-rate breakthrough. No default training configuration was silently changed.

Compute: 80,003,072 new decisions across eight runs; 2,313.8 seconds (38.6 minutes)
of measured training. Training plus scheduled evaluations took 3,098.3 seconds;
the final test panel took another 222.2 seconds, about 55.3 minutes in total.
Individual anchored 10M runs take about 300 seconds of training versus roughly
249 seconds for the earlier unanchored control. No jobs remain queued.

Artifacts:
- `results/autoregressive-anchor-screen.json`: feature and policy-strength screen.
- `results/autoregressive-anchor-policy1.json`: stronger policy constraint.
- `results/autoregressive-anchor-policy01-replicates.json`: PPO seeds 1 and 2.
- `results/autoregressive-anchor-navigation.json`: protection outside combat.
- `results/autoregressive-anchor-holdout.json`: all paired test episode outcomes.
- `results/autoregressive-anchor-summary.json`: three-seed aggregate and compute.
- `results/autoregressive-anchor-efficiency.json`: paired common-success intervals.
- `results/autoregressive-anchor-drift.json`: fixed-observation function/weight audit.

Reproduce the final statistics with
`gpu-d1/.venv/bin/python gpu-d1/diagnostics/autoregressive-imitation/anchor_summary.py`.
The training/evaluation entry points are adjacent in that diagnostics directory.

### Navigation-only continuation to 30M

Launched September 16 at 22:40 Halifax time: continue `navigation1-seed0`
from 10,000,384 decisions to 30,000,128, with validation at 20M and 30M.
This retains the optimizer, environment and RNG states, the original imitation
reference, weight-1 navigation-only KL, and all existing reward/PPO settings.
All layers remain trainable. The question is whether the small efficiency gain
persists or grows without loss of clear rate over longer training.

The queue then repeats sampled and greedy evaluation on the same 100 test maps
and 16 placements per map, paired with initial imitation. These are reused test
scenarios, not a new untouched panel. Expected additional runtime is 12–14
minutes, including validation and test evaluation.

Launcher: `diagnostics/autoregressive-imitation/continue_navigation_30m.py`.
Status and logs: `learning-runs/autoregressive-anchor-navigation-30m/`.
Results will be written to `results/autoregressive-anchor-navigation-30m.json`
and `results/autoregressive-anchor-navigation-30m-holdout.json`.

Completed: 30,000,128 decisions, including both validation checkpoints and the
paired test evaluation. The additional 20M took 598.5 seconds of training and
720.4 seconds overall (12.0 minutes). Cumulative training time is 900.6 seconds.

| Checkpoint | Validation sampled clears | Validation greedy clears | Successful turns sampled / greedy |
|---|---:|---:|---:|
| 10M | 96.29% | 94.53% | 672.7 / 672.9 |
| 20M | 95.31% | 93.95% | 671.8 / 657.4 |
| 30M | 96.39% | 94.82% | 672.3 / 664.2 |

On the repeated test panel (1,600 episodes per evaluation):

| Checkpoint | Sampled clears | Greedy clears | Successful turns sampled / greedy |
|---|---:|---:|---:|
| Initial imitation | 96.75% | 93.56% | 675.3 / 675.0 |
| Navigation-only 10M | 96.88% | 93.75% | 674.3 / 668.2 |
| Navigation-only 30M | 96.44% | 93.56% | 669.8 / 663.4 |

Comparing only episodes both policies clear, 30M saves 6.24 sampled turns
relative to imitation (95% map-bootstrap interval 2.77–9.83 saved, 1,512 common
clears), and 12.41 greedy turns (9.36–15.45 saved, 1,451 common clears).
Relative to 10M, it saves 4.22 sampled turns (0.40–8.14) and 5.36 greedy turns
(1.61–9.21). These intervals resample the 100 map clusters 10,000 times with
seed 713, using the ratio of summed paired turn differences to common-clear
counts, preserving all placements for each sampled map.

Clear-rate differences versus imitation remain inconclusive: sampled -0.31
percentage points (95% interval -1.38 to +0.69), greedy 0.00 points (-1.13 to
+1.13). Overall return differences also include zero. At 30M, sampled test
deaths/timeouts are 3.13%/0.44%; greedy deaths/timeouts are 3.13%/3.31%.

This extends the evidence for preventing catastrophic degradation through
30M with all layers trainable. The modest efficiency improvement grows, but
there is still no demonstrated clear-rate or overall-return improvement.
Common-clear efficiency is conditional on success, not a measure of total
policy quality; one training seed and reused test scenarios remain limitations.
No jobs remain running or queued in this continuation.
