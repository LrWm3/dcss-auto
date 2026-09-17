# Training to avoid ordinary-map deaths in the D1 stairs task

This experiment starts from the frozen adapted D1 stairs checkpoint. It trains
crowd handling and retreat on actual **training-map** failures, then checks
whether any improvement transfers to full floors. The 58 previously audited
test deaths are not training examples. Their analysis informed the experiment
design, so the old test layouts are not a wholly untouched research benchmark.

The task remains 24 enemies, three hidden stairs, 2,048 physical turns, local
wall-blocked LOS, ordinary directional actions and REST, +1 for descending,
and -0.00001 per physical turn. There is no new combat reward or heuristic
action override during PPO or evaluation.

## Training data and corrections

The source policy samples actions in 1,024 ordinary training worlds, retaining
the existing training distribution (including its existing clumping setting).
Collection stops at 96 deaths or 2,048 collection steps. Each death contributes
the states eight and 32 policy decisions earlier, clamped to that episode's
start. Thus the bank emphasizes early failures, and some snapshots may repeat
the same episode-start state. It is not an unbiased sample of encounters.
Ordinary rollout observations also provide a capped retention buffer.

For each snapshot, every legal first action is screened with 16 new simulator
RNGs, followed by the unchanged greedy source policy until exit/death/timeout.
The best action becomes a candidate if it improves estimated exit probability
by at least 25 percentage points over the source's greedy first action.
These candidates are frozen before independent confirmation: 64 fresh RNGs,
paired between candidate and source action. A label is accepted only with
at least 50% exit success and a 20-point improvement. These are practical
screening thresholds, not formal significance tests. Future randomness affects
movement and combat; different actions consume random draws differently.

Labels change only the selected first action. They do not teach the policy a
future RNG or expose simulator state as an observation. The full native state
is used solely to initialize repeated training encounters.

## Two matched-budget continuations

Both arms start from the same checkpoint with fresh Adam and seed 0. Both use
the existing PPO settings (gamma 1, lambda .95, learning rate .0003, 512 worlds,
64-step rollouts, four epochs, 4,096 minibatches, zero entropy bonus), the
existing navigation KL, and weight-.5 source-policy KL on the collected
ordinary observations to retain useful behavior.

- **Control:** ordinary full-floor PPO.
- **Targeted:** 384 ordinary worlds plus 128 worlds repeatedly reset to the
  death-state bank with fresh future RNG. Add weight-.5 cross-entropy on
  independently confirmed action corrections (128 examples per minibatch).

The treatment combines encounter resets and supervised action corrections;
this first pass does not isolate their separate effects. Both arms train to
5,000,192 policy decisions with checkpoints at 500,224, 1,000,448, 3,000,320,
and 5,000,192. Physical turns, practice decisions, training time, and data
preparation time are reported separately. Preparation and supervised examples
are additional compute, not included in the PPO decision count.

## Evaluation and selection

Each checkpoint gets 1,024 full-floor validation episodes in sampled and
greedy modes, without resets or corrections. Select the endpoint with the
highest mean sampled/greedy exit rate, including the frozen baseline as a
candidate. Freeze that selection before the final comparisons:

- 6,400 episodes on the 100 test maps with new placements/RNG, seed 790011.
- The original 3,200-episode cohort, seed 950991, as a regression check.

Compare exit, death, timeout, and turn counts with the baseline and matched
control. Report paired map-cluster bootstrap intervals; these do not cover
training-seed variability. Lower deaths alone are insufficient if replaced by
timeouts. The original 58 cases can show regression fixes, but the fresh
cohort is the main check of transfer to new episodes.

## Running and storage

```sh
gpu-d1/.venv/bin/python -u gpu-d1/diagnostics/d1-stairs-survival/run.py
gpu-d1/.venv/bin/python gpu-d1/diagnostics/d1-stairs-survival/summarize.py
```

The process holds a suite lock and saves checkpoints/status under the ignored
`gpu-d1/learning-runs/d1-stairs-survival/`. Disk budget: 4 GiB total, 10 GiB
free-space reserve. SIGTERM/SIGINT requests a save and stop at a PPO update
boundary; preparation stages finish before the stop is handled. Existing
preparation artifacts and training checkpoints resume automatically. Changes
to recorded source files or checkpoints require a new suite directory.

Final results are written to `gpu-d1/results/d1-stairs-survival.json`.
The summarizer verifies reproduction of the original baseline, checks learned
probabilities for the correction labels, and records compact counts and paired
regressions in `gpu-d1/results/d1-stairs-survival-summary.json`. It also compacts
the full JSON without dropping any outcomes.

## Completed first pass

Both arms completed 5,000,192 PPO decisions; validation selected the 5M
checkpoint in both. Collection used 336,896 decisions and found 96 deaths,
yielding 192 snapshots and 10,624 retention observations. Of 38 candidate
action changes, 20 passed independent confirmation: 17 moves and three attacks.
The targeted model greedily selects all 20 labels after training, compared with
zero at the start and one for the control. This is training-set acquisition,
not evidence of generalization by itself.

Full greedy rollouts from those 20 fitted scenes, with **64 new simulator
RNGs each after training**, do improve: baseline 546/1,280 exits (**42.7%**),
targeted 1,100/1,280 (**85.9%**), control 815/1,280 (**63.7%**). This confirms
better survival on the practice situations, not just matching a first-action
label. The geometries and starting states were used in training, so this is
still an acquisition check rather than a held-out capability test.

On **6,400 fresh episodes per mode**, using new placements/RNG on the existing
100 test layouts:

| Model | Sampled exits / deaths / timeouts | Greedy exits / deaths / timeouts |
|---|---|---|
| Frozen baseline | 6,275 / 125 / 0 | 6,213 / 105 / 82 |
| Targeted 5M | 6,281 / 119 / 0 | 6,217 / 97 / 86 |
| Ordinary control 5M | 6,274 / 126 / 0 | 6,207 / 98 / 95 |

Targeted training reduces observed deaths, but its exit-rate gains over the
baseline are only **+0.094 percentage points sampled** (paired map-cluster 95%
interval -0.250 to +0.438) and **+0.063 points greedy** (-0.328 to +0.469).
Neither establishes a population improvement. Greedy timeouts increase by
four, partially offsetting the eight fewer deaths. Targeted training also has
slightly more exits than the control, without a conclusive advantage.

The original 3,200-episode regression cohort gives:

| Model | Sampled exits / deaths / timeouts | Greedy exits / deaths / timeouts |
|---|---|---|
| Frozen baseline | 3,141 / 58 / 1 | 3,113 / 48 / 39 |
| Targeted 5M | 3,147 / 53 / 0 | 3,122 / 41 / 37 |
| Ordinary control 5M | 3,138 / 62 / 0 | 3,105 / 50 / 45 |

These differences also have intervals spanning zero. Baseline outcomes are
checked against the prior D1 report exactly. The compact summary includes
previously fatal episodes rescued **and newly introduced deaths**, rather than
counting only repaired failures.

In sampled regression play, targeted training turns **37 of the original 58
deaths into exits**, but introduces **32 new deaths**, leaving 53 deaths in
total. Inference on the earlier corridor example (episode 1607's exact fatal
state) still selects ATTACK NW rather than the beneficial MOVE E. That example
was not trained on. Its east-move probability remains about 0.034%, so this
pass has not acquired a general corridor-retreat rule that fixes that case.

Preparation took **147 seconds**, targeted PPO **217 seconds**, and control
PPO **198 seconds**. The full pipeline, including checkpoint validation and
final full-floor comparisons, took **1,010 seconds (16.8 minutes)**; the extra
post-training practice diagnostics are outside that wall time. Targeted PPO
represented 6,302,440 physical turns, including 1,250,048 policy decisions in
reset practice worlds. Control represented 6,069,417 physical turns.

This pass learns the supplied corrections and produces small favorable point
estimates on full floors. It does **not** demonstrate a reliable general
reduction in deaths. The next question is whether a broader set of verified
failure situations transfers better; simply fitting these 20 labels harder
has little room left. No checkpoint is automatically promoted over the frozen
baseline.

Results: [compact summary](../../results/d1-stairs-survival-summary.json) and
[complete paired outcomes](../../results/d1-stairs-survival.json). Selected
checkpoints remain in the ignored suite directory under
`targeted/checkpoints/5000192.pt` and `control/checkpoints/5000192.pt`.
