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
