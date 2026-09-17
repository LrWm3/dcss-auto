# Improving ordinary-floor clears

This study starts from `autoregressive-survival/runs/exploration-seed0/latest.pt`
at 35,000,320 decisions, the shared starting checkpoint of the preceding tactical
study. The objective is actual ordinary-floor clears, not performance on constructed
encounters. Ordinary floors have 24 enemies, wall LOS, 2048 physical turns, and
MOVE/ATTACK directions plus WAIT and REST. Reward remains +1 clear minus 0.00001
per physical turn. The model architecture and runtime actions are unchanged.

## Diagnosis

On the existing 1,024-episode validation panel, the source clears 96.09% sampled
and 94.34% greedy. Greedy failures comprise 34 deaths and 24 timeouts; all 24
timeouts contain repeated two-square movement loops.

Observation-only interventions on the greedy source produce:

| Intervention | Clear | Death | Timeout |
|---|---:|---:|---:|
| None | 94.34% | 3.32% | 2.34% |
| Always attack weakest adjacent enemy | 94.53% | 3.03% | 2.44% |
| Wait if awake enemy visible, none adjacent | 95.61% | 2.05% | 2.34% |
| Both combat rules | 94.92% | 2.73% | 2.34% |
| Native controller outside awake encounters | 96.29% | 2.83% | 0.88% |
| Full native controller | 96.29% | 2.64% | 1.07% |

Under sampled model actions, overriding combat raises clears from 96.09% to 98.05%.
Interventions change subsequent trajectories and RNG consumption; the table is a
rollout comparison, not a guarantee of survival from every individual failure.
The native controller is imperfect, including navigation loops. It uses visible
enemies and remembered terrain, not hidden enemy coordinates.

## Training screen

Three +1,000,448-decision arms share the same source policy, optimizer, ordinary
world states, and training RNG. The previous practice worlds are removed for every
arm, restoring their parked ordinary states from the source checkpoint. Thus all
training decisions are on the 256 ordinary training maps (the existing one-third
clumped placement mixture). Validation uses separate, unclumped layouts.

- Control: PPO plus the existing original-imitation navigation KL anchor.
- Wait: additionally minimize cross-entropy for WAIT when an awake enemy is visible
  and none is adjacent; weight 0.1, normalized over eligible minibatch observations.
- Teacher: additionally minimize cross-entropy for the native controller's action
  on all current rollout states; weight 0.3.

Labels are collected on the student's **own training trajectories**. The policy
still samples its own rollout actions. No evaluation observations enter training,
no rewards change, and there are no action overrides in learned-policy evaluation.
These are supervised corrections alongside PPO, not evidence of unaided PPO
improvement. The original navigation anchor is retained in all arms for stability.

The screen evaluates at +500,224 and +1,000,448 decisions. The intended final
comparison uses the 1M endpoints. Any selected follow-up is based on validation,
with the 100-map test split reserved for final confirmation on new placements.
We require improvement against the source, not merely against a decaying control.

`ordinary_eval.py` audits legal actions, reward accounting, terminal episodes,
loop failures and observation-only combat label parity against the native
controller. `teacher_audit.py` checks navigation and full-controller interventions.
`run_ordinary.py` runs the three arms sequentially with a 4 GiB suite storage cap,
10 GiB free-space reserve, atomic checkpoints, and recorded source hashes.
Checkpoints and map assets remain ignored by git. The copied runner differs only
in its optional supervised correction loss; the existing native libraries are
reused unchanged. Training time includes producing controller labels.
