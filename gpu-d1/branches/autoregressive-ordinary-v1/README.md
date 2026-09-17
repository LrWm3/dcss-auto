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

Action overrides using only available observations on the greedy source produce:

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

## Completed ordinary-only screen

All rows below use the final +1M checkpoint and 1,024 validation episodes.

| Arm | Sampled clears | Greedy clears | Added training time |
|---|---:|---:|---:|
| Starting checkpoint, 35M | 96.09% | 94.34% | — |
| Matched ordinary PPO control | 95.12% | 93.65% | 29.5 s |
| Waiting correction | **97.66%** | **94.82%** | 30.3 s |
| Full-controller correction | 97.36% | 93.95% | 35.2 s |

The waiting arm was selected by the largest mean sampled/greedy validation clear
at the final endpoint among the two correction arms. Selection and checkpoint
hashes were saved before test evaluation. No endpoint was chosen using test scores.

### Confirmation on 100 held-out layouts

Each mode uses 3,200 episodes, 32 placements per map, seed 940021. These layouts
were excluded from training and validation. The policy chooses every action itself.

| Model | Sampled clears | Deaths | Timeouts | Greedy clears |
|---|---:|---:|---:|---:|
| Starting checkpoint | 3,094 / 3,200 (96.69%) | 93 | 13 | 94.88% |
| Matched PPO control | 3,057 / 3,200 (95.53%) | 129 | 14 | 94.88% |
| Waiting correction | **3,123 / 3,200 (97.59%)** | **72** | **5** | 94.53% |

The sampled improvement over the source is **+0.906 percentage points**: 29 more
clears, or 27% fewer failures. A paired bootstrap resampling the 100 map clusters
(20,000 replicates) gives a 95% interval of **+0.188 to +1.656 points**. Against
the matched continuation, the gain is +2.063 points [1.250, 2.906]. This measures
evaluation uncertainty for one trained seed, not reliability across training seeds.

Greedy improvement was not established: -0.344 points [-1.156, +0.469] versus the
source. Greedy deaths fell from 83 to 73, but timeouts increased from 81 to 102;
101 of the candidate's 102 timeouts exhibited repeated two-square movement loops.
The method fixes some combat behavior and does not fix greedy navigation loops.

The sampled source averages 75 MOVE actions per floor while an awake enemy is
visible and none is adjacent; the corrected policy averages 0.116. This statistic
counts moves in that state, not their direction. Multi-adjacent exposure falls
from 13.56 to 9.71 turns per floor. Different trajectories also change random-number
consumption; the 29-clear net difference is not an individual causal rescue count.

### Tactical regression and bounded follow-up

On the previous 512-episode tactical checks, ordinary-only correction loses skill:

| Checkpoint | Original tactics sampled / greedy | Far-cover tactics sampled / greedy |
|---|---:|---:|
| Starting 35M | 79.88% / 80.86% | 50.78% / 54.88% |
| Ordinary waiting correction, 36M | 73.44% / 74.61% | 45.31% / 42.38% |
| Prior balanced tactics, 40M | 86.52% / 86.72% | 86.91% / 87.11% |

Consequently the 36M candidate is an ordinary-floor specialist, not a replacement
for the stronger tactical checkpoint.

A bounded follow-up starts both arms from the prior balanced 40M checkpoint and
continues for +1,000,448 decisions, preserving its 51/512 tactical practice worlds,
practice temperature, simulator/optimizer/RNG state, and navigation anchor. One
arm adds no correction; the other applies weight-0.1 waiting correction **only on
ordinary worlds with one or two visible awake enemies and none adjacent**. The
model receives no new observations, actions or rewards. The restriction does not
prevent gradient changes from affecting other states.

Validation results at 41M: control 94.92% sampled / 94.73% greedy; correction
96.88% / 94.34%. Training takes 38.2 / 34.2 seconds respectively (900,794 ordinary and 99,654 tactical
decisions per arm). On the original
tactical panel, correction still regresses to 83.79% sampled / 78.71% greedy,
compared with 86.72% / 86.33% for its matched control. Retaining practice reduces
some forgetting but does not establish preservation of tactical skill. On the
far-cover panel the corrected policy retains 86.72% sampled and greedy, versus
87.11% for both modes of the matched control and 86.91% / 87.11% for its 40M source.

The follow-up is evaluated on the same 100 test layouts with fresh placements,
seed 940121, including both the original 35M and immediate 40M source. This is a
follow-up on a previously inspected test split, not a newly untouched map holdout.
Its design was motivated by tactical regression and validation, not test tuning.

The follow-up test confirms no clear improvement over either source:

| Checkpoint | Sampled clears | Greedy clears |
|---|---:|---:|
| Original 35M source | 96.53% | 94.59% |
| Immediate balanced 40M source | 96.69% | 94.56% |
| Matched 41M control | 96.19% | 95.13% |
| Restricted waiting correction, 41M | 96.88% | 93.91% |

Its sampled difference from the immediate source is +0.188 points, with map-cluster
95% interval [-0.531, +0.906]; from the original source, +0.344 [-0.469, +1.188].
The greedy candidate has 75 deaths and 120 timeouts, compared with 94 and 80 for
its immediate source. Fewer deaths again fail to yield more greedy clears because
navigation timeouts increase. We do not promote this follow-up as an improvement.

The demonstrated result is therefore narrow: **additional waiting supervision can
raise sampled ordinary-floor clears beyond the 35M source, but neither the greedy
navigation problem nor simultaneous retention of all retreat skills is solved.**
Further PPO alone in the matched arms did not establish an improvement.

## Artifacts and reproduction

- `results/autoregressive-ordinary-screen.json`: all three training curves.
- `results/autoregressive-ordinary-confirmation.json`: first test confirmation,
  individual outcomes and paired map-cluster intervals.
- `results/autoregressive-ordinary-tactical-regression.json`: first regression check.
- `results/autoregressive-ordinary-retain.json`: matched tactical-retention follow-up.
- `results/autoregressive-ordinary-retain-confirmation.json`: follow-up test outcomes.
- `results/autoregressive-ordinary-retain-tactical-regression.json`: follow-up far-cover check.
- `diagnostics/ordinary-clears/{confirm,regression,retain,confirm_retain,regression_retain}.py`:
  evaluation and follow-up entry points; run with `gpu-d1/.venv/bin/python` from the
  repository root. Training manifests hash the exact source files used at launch;
  later diagnostic-label edits intentionally cause manifest drift on a relaunch.

First candidate checkpoint:
`learning-runs/autoregressive-ordinary/runs/wait-seed0/latest.pt` (36,000,768 decisions).
Follow-up candidate checkpoint:
`learning-runs/autoregressive-ordinary-retain/runs/wait-seed0/latest.pt` (41,000,960).
All five additional training arms together take about **167 seconds** of measured
training, excluding evaluation, initialization and serialization. There is one
training seed. Native simulator code and model architecture remain unchanged.
