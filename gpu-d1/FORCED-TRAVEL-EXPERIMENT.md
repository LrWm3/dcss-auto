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
