# Removing the choice to travel

2026-09-15. Two fresh seed-0 PPO runs, 30M outer decisions each, 15x15
wall-blocked vision, local enemy knowledge, LOS-gated waking, 24 normal enemies,
zero ogres. All other rewards, observations and PPO settings match the original
15x15 optional-travel experiment. Both retain the frontier pointer and route hint.

Whenever the existing frontier travel action is available, the action mask
permits only that action. The policy cannot opt out. When travel is unavailable,
the ordinary movement/attack/wait mask applies. This includes visible enemies
(sleeping or awake), but also the exceptional case of no reachable nonzero
frontier route. Travel still stops at its fixed target or the first enemy
sighting, and never chains multiple targets inside one decision.

| Variant | Episode deadline |
|---|---|
| `forced_turn512` | 512 physical game turns, including steps inside travel |
| `forced_decision512` | 512 outer transitions; each complete/interrupted trip counts once |

The first variant directly tests removing travel as a policy choice against the
existing optional-travel model. The second additionally changes available game
time. Its final trip executes normally before decision timeout is applied;
clear or death during the trip takes precedence. Both report physical episode
turns and decision counts. The normalized time input reflects the applicable
budget. Reset clears both clocks. There is no separate 512-turn cap in the
decision-budget variant.

Forced transitions remain in PPO rollouts and count toward the 30M budget. Their
categorical distribution has one allowed action, giving zero action-choice
entropy/policy gradient at those states; value learning and reward propagation
continue. Gamma/GAE remain per outer transition with summed macro rewards,
matching the optional-travel implementation. This does not compare equal
numbers of freely chosen actions, physical turns, or training seconds.

Report final sampled clear/death/timeout, kills, exploration, reward, training
seconds, physical training turns, and episode travel/decision counts. The
existing evaluator uses 32 validation layouts x 32 episodes, plus greedy
evaluation, without touching the test split. Compare final checkpoints; one seed
is a screen, not evidence of a reproducible advantage.

Implementation: `branches/vision15-forced-travel-v1`. Existing suites and their
checkpoints remain unchanged. Storage retains latest/best checkpoints under a
2 GiB cap and 5 GiB free-space reserve; generated files use existing ignore rules.

```sh
gpu-d1/.venv/bin/python gpu-d1/branches/vision15-forced-travel-v1/scripts/run_ring_ablations.py \
  --output gpu-d1/learning-runs/vision15-forced-travel-30m --steps 30000000 --seeds 0
```

Validation entry point: `scripts/test_forced_travel.py <smoke-suite>`.
It checks CPU/CUDA parity, forced masks, LOS eligibility, reward accounting,
clock/reset semantics, active-world freezing, both deadline boundaries including
a multi-turn final trip, and physical-budget trajectory equivalence with the
original optional-travel simulator given identical actions.

Validation passed for both arms: 8,400 CPU/CUDA outer transitions each,
10,198/10,835 physical turns, and 799/994 forced trips respectively. Explicit
native boundary tests verify completion of the last trip under decision timeout,
mid-trip stopping under physical timeout, and reset of both clocks. A further
8,400 matched-action transitions reproduce original optional-travel dynamics.
Artifact: `results/vision15-forced-travel-validation.txt`.

The sequential full suite was launched in the background after these checks.
Log: `results/vision15-forced-travel-30m-console.log`. Expected completion roughly
10-15 minutes after launch, subject to the decision-budget arm's longer episodes.

## Completed training and fixed-policy deadline transfer

Both full runs completed at 30,015,488 outer decisions. The physical-budget
model trained for 278.001 seconds and cleared 22.27%; the decision-budget model
trained for 322.761 seconds and cleared 88.28% on sampled validation.

To separate learned behavior from the evaluation deadline, evaluate the **final
physical-budget checkpoint without further training** in both environments:

| Evaluation of the same turn-trained policy | Clear | Death | Timeout | Mean game turns |
|---|---:|---:|---:|---:|
| Original 512-turn deadline and clock | 22.27% | 11.52% | 66.21% | 458.16 |
| 512-decision deadline and decision clock | 87.11% | 12.60% | 0.29% | 541.25 |
| 512-decision deadline, original physical clock | 87.79% | 12.01% | 0.20% | 545.00 |

Each row uses the same 32 validation maps x 32 episodes and evaluation seed.
The original sampled and greedy aggregate metrics reproduce exactly. No model
or optimizer updates occur, and the source checkpoint hash remains unchanged.
The physical-clock control exposes elapsed game turns / 512, without clipping,
so it can exceed the training input range after the old deadline. The primary
transfer uses the decision-clock semantics of the new environment instead.

The large gain therefore does not require learning under the longer deadline:
the existing policy can already finish many episodes when allowed more time.
This does not establish an advantage of forced over optional travel at the new
deadline, nor statistical equivalence to the decision-trained policy. These
remain results for one training seed and the validation split.

```sh
gpu-d1/.venv/bin/python gpu-d1/branches/vision15-forced-travel-v1/scripts/evaluate_deadline_transfer.py \
  --suite gpu-d1/learning-runs/vision15-forced-travel-30m \
  --output gpu-d1/results/vision15-forced-travel-deadline-transfer.json
```

The result artifact includes sampled and greedy outcomes and per-map metrics,
checkpoint/library/script hashes, and evaluation time.

## Applying forced travel to previously trained policies

`scripts/evaluate_policy_transfer.py` evaluates the optional-travel 30M model,
the no-travel 30M model, and its 42.66M time-matched continuation. All use the
same 15x15 observation schema and no-ogre enemy statistics. No weights change.
Each model is evaluated under its original rules, forced travel with 512 game
turns, forced travel with 512 decisions, and the latter with its original
physical-turn clock input retained as a control.

For nine-action no-travel models, an external controller supplies action 9 when
the forced environment enables it. The original actor handles all other states.
Implementation appends a fixed travel logit to the original nine logits, with
the mutually exclusive forced-action mask; it adds no learned parameters. For
the ten-action optional-travel model, the forced mask is applied directly.

Validation reproduces the original sampled and greedy outcome rates, kills,
and episode turns, with a 1e-7 tolerance for floor coverage due to CPU/GPU mean
rounding. Corpus and library hashes are verified, source checkpoint hashes are
checked unchanged after evaluation, and both modes/per-map metrics are retained.
Nine-to-ten action adaptation can change sampled RNG trajectories, so individual
episodes are not claimed to be paired counterfactuals.

```sh
gpu-d1/.venv/bin/python gpu-d1/branches/vision15-forced-travel-v1/scripts/evaluate_policy_transfer.py \
  --output gpu-d1/results/vision15-forced-travel-policy-transfer.json
```

Completed sampled validation (clear rates):

| Fixed source model | Original rules | Forced, 512 turns | Forced, 512 decisions | Decision deadline, physical clock |
|---|---:|---:|---:|---:|
| Optional travel, 30M | 19.73% | 21.19% | 85.16% | 83.40% |
| No travel, 30M | 20.02% | 18.85% | 77.54% | 75.20% |
| No travel, 42.66M | 19.73% | 21.78% | 80.66% | 79.88% |

Forced travel with the same physical deadline has small, mixed effects. Adding
the decision deadline produces large gains even for policies never trained with
travel. Thus training with the macro is not necessary to obtain most of this
completion gain in this toy task. The optional-travel policy remains stronger
than these no-travel policies under the new controller/budget in this seed.
These comparisons do not isolate automatic travel from the added game time in
the decision-budget columns; optional control with an extended physical deadline
would be a separate experiment. Aggregate original evaluations reproduce as
specified above, and all checkpoint immutability checks passed.

## Estimating a less restrictive physical-turn limit

Replayed the five fixed policies under forced travel, 512 outer decisions and
the decision clock. Each replay reproduces its earlier sampled clear rate
exactly; no training occurs. Turns below are conditional on successful clearing:

| Source policy | Median | 95th percentile | 99th percentile | Maximum |
|---|---:|---:|---:|---:|
| Optional travel, 30M | 589 | 769 | 898 | 976 |
| No travel, 30M | 602 | 758 | 855 | 950 |
| No travel, 42.66M | 591 | 780 | 878 | 980 |
| Forced, turn-trained | 597 | 768 | 899 | 961 |
| Forced, decision-trained | 592 | 760 | 870 | 986 |

A 768-game-turn cutoff would truncate 33-47 observed successful episodes per
1,024 evaluation episodes, depending on policy. At 896, 4-10 successful episodes
would be truncated; at 1,024, none. Thus 1,024 turns is a reasonable candidate
for a mostly non-limiting budget for these policies on this validation set.
1,280 would add margin, but its benefit is not demonstrated by these traces.

These are retrospective cutoffs of trajectories produced with a different clock,
not direct evaluations under a new physical deadline. Changing the normalized
clock may change behavior. Episodes already censored by the 512-decision limit
(0.1-1.6%, depending on policy) do not tell us how long eventual clears might
take, and unseen maps can have longer tails. This is not a universal guarantee.

Script: `scripts/evaluate_turn_distribution.py --output <path>`.
Artifact: `results/vision15-forced-travel-turn-distribution.json` includes full
metrics, all-episode and clear-only turn distributions, and counts of successful
clears/ongoing episodes at candidate cutoffs. Source/checkpoint/library hashes
are recorded and original checkpoints remain unchanged.

## Frozen-policy validation without forced travel, 2048 game turns

`scripts/evaluate_unforced_2048.py` evaluates the same five checkpoints without
forced travel or retraining. Nine-action models retain movement/attack/wait;
ten-action models may select travel under its original availability rules.
The original optional/no-travel native libraries enforce a physical deadline of
2,048 turns through their existing runtime ABI. Macro steps consume that budget
and are interrupted at the deadline. There is no separate 512-decision cap.

Primary evaluation supplies elapsed physical turns / 2048 as the clock input.
A sensitivity evaluation preserves the training clock: physical turns / 512 for
four policies, outer decisions / 512 for the decision-trained forced policy.
The latter controls can exceed the original training input range. Both sampled
and greedy evaluation use the existing 32 validation layouts x 32 episodes and
seed 900000. This is validation-only; no test maps or optimizer updates are used.

The forced-trained policies never learned whether to select travel when it was
available: their training mask made that choice deterministic. Removing that
mask is therefore a policy-distribution change, and their optional-travel behavior
must not be interpreted as a policy trained to make that choice.

The evaluator verifies corpus/library/checkpoint hashes, retains the original
action-head size, checks that ordinary wait remains available alongside travel,
and asserts that every episode ends by 2,048 game turns and every timeout occurs
exactly there. It records unchanged checkpoint hashes after evaluation.

```sh
gpu-d1/.venv/bin/python gpu-d1/branches/vision15-forced-travel-v1/scripts/evaluate_unforced_2048.py \
  --output gpu-d1/results/vision15-unforced-2048.json
```

Completed sampled validation, no additional training:

| Source policy | Clear, budget clock | Death | Timeout | Mean turns | Clear, training clock |
|---|---:|---:|---:|---:|---:|
| Optional travel, 30M | 83.59% | 16.21% | 0.20% | 528.15 | 82.42% |
| No travel, 30M | 77.34% | 21.78% | 0.88% | 527.32 | 75.29% |
| No travel, 42.66M | 82.91% | 15.92% | 1.17% | 559.62 | 80.47% |
| Forced, turn-trained | 87.89% | 11.72% | 0.39% | 990.61 | 81.45% |
| Forced, decision-trained | 89.06% | 10.84% | 0.10% | 989.81 | 79.30% |

Timeouts are rare with the budget-normalized clock. No-travel policies show
large completion gains without any macro action, supporting the conclusion that
the old physical deadline was a major bottleneck. Formerly forced policies
still finish many episodes, but now take about 990 turns on average and choose
travel less often; removing the forced mask changes their navigation behavior.
The earlier roughly-1,024-turn estimate was based on forced-travel trajectories,
so it should not automatically be applied to this changed controller.

Clock sensitivity is material for forced-trained policies, especially the one
trained with a decision clock. Its preserved-clock control clears 79.30%, with
7.03% timeouts and 13.67% deaths; it now sees decision/512 values beyond training.
These are single-seed frozen-policy comparisons with changed evaluation inputs,
not evidence that any source training approach is reproducibly superior.

Artifact: `results/vision15-unforced-2048.json` contains both evaluation modes,
both clock conventions, per-map metrics, turn distributions, and provenance.
All physical-deadline and checkpoint-immutability checks passed.
