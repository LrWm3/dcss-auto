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
| feature10-seed0 | 81.74% | 0.00% | 1559.4 | 0.0 | 253.5 |
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
