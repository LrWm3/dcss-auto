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
