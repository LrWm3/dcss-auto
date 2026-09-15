# Frontier travel macro, v1

2026-09-15. Implementation: `branches/vision-frontier-travel-v1`.

Action 9 (`go_to_nearest_frontier`) travels all the way to the nearest reachable
frontier selected at activation, rather than issuing just one directional step.
It chooses the same target and tie break as the existing frontier observation.
The precomputed route uses only remembered floor. It remains fixed even if
intermediate discoveries change which tile would now be the nearest frontier.
It does not chain travel to another frontier upon arrival.

The action is masked while any living enemy (including a sleeping enemy or an
ogre) is in the player's current LOS, and when no nonzero reachable route exists.
It becomes available again when those conditions clear. Each internal step is a
normal game turn: movement, exploration, regeneration, monster waking, energy,
combat, rewards, death, and the 512-turn deadline all still apply. Travel stops on
arrival, the first turn with an enemy sighting, an unexpected obstruction, or
terminal outcome. Sightings are checked after player movement and during/after
monster actions, so a transient sighting still interrupts before another player
step. The triggering game turn completes normally; travel grants no free enemy
turn cancellation. It never continues into an automatically reset episode.

Invalid direct calls to the masked action fall back to one wait turn and are
counted separately. The PPO policy cannot select masked actions. No new enemy
knowledge is added to the 502-input observation; the action head grows from nine
to ten choices.

## Training comparison

Fresh seed 0, 30M **policy decisions**, 256 training maps, the same 32 validation
maps × 32 episodes. Task: 24 ordinary enemies, 2 optional slow ogres, 512 physical
turns, local enemy information, wall-blocked radius-four player vision, radius-six
LOS-gated monster waking, optional-role label off. Same rewards and PPO settings
as `vision-ogre2-wake-screen-30m/ogre2_wake_los-seed0`, the no-macro comparator.
No transfer from that model or the no-ogre 100M continuation.

Per user request, v1 treats the entire trip as **one PPO transition**. The reward
is the undiscounted sum of all internal turn rewards; gamma 0.99 and GAE lambda
0.95 apply once per policy decision, without duration correction. This changes
temporal credit assignment as well as the action set. Thirty million policy
decisions can represent more than thirty million physical game turns, so an
improvement at that budget is not evidence of greater sample efficiency per
underlying turn. Physical episode deadlines remain 512 turns.

Suite: `learning-runs/vision-frontier-travel-30m`.
Log: `results/vision-frontier-travel-30m-console.log`.
Launch metadata and dry-run plan are adjacent to the log. Disk retention is the
existing bounded latest/best checkpoint scheme (2 GiB cap, 5 GiB free reserve).

```sh
gpu-d1/.venv/bin/python gpu-d1/branches/vision-frontier-travel-v1/scripts/run_ring_ablations.py \
  --output gpu-d1/learning-runs/vision-frontier-travel-30m --steps 30000000 --seeds 0
```

## Measurements

Retain clear/death/timeout, exploration, required-enemy discovery, and all ogre
diagnostics. Add physical turns per policy decision, travel uses, travel turns,
mean trip duration, arrivals, enemy interruptions, terminal stops, and invalid or
blocked travel. Arrivals/interruptions/terminal flags may coincide on the last
step of a trip, so these are not exclusive categories.

Training checkpoints, curves and results record cumulative physical turns and
travel use alongside policy decisions and training seconds. Evaluation records
both decision counts and actual episode turns. Training `work_totals` columns:
physical turns, valid travel uses, travel turns, arrivals, enemy interruptions,
terminal stops, invalid/blocked requests. Native output slots 26–32 carry these
per-transition values; output 33 is an internal transient-sighting flag, replaced
by the episode policy-decision count in evaluation's terminal summary only.

## Validation

End-to-end smoke passed. `results/vision-frontier-travel-validation.txt` records:

- Native explicit-step replay matches macro rewards, final state, event sums,
  interruption and timeout/reset behavior.
- The macro is disabled while an enemy is visible and enabled when clear;
  absent frontiers and invalid requests are handled without zero-time decisions.
- CPU/CUDA outputs, observations and masks match over 8,400 policy transitions,
  exercising 1,083 travel uses spanning 3,150 internal travel turns.
- Per-turn rewards, episode clocks, active masking and ogre diagnostics remain
  consistent. Hidden-enemy/terrain information tests still pass.
- An additional 8,400 ordinary-action turns exactly match the original two-ogre
  LOS-wake environment's observations, original action masks and diagnostics.


## Follow-up queue: turn budget and ogres

`results/vision-budget-comparison-queue.json` queues four fresh seed-0 30M runs:

| Order | Ogres | Physical turn deadline | Travel |
|---|---:|---:|---|
| 1 | 2 | 1024 | Off |
| 2 | 2 | 1024 | On |
| 3 | 0 | 512 | Off |
| 4 | 0 | 512 | On |

All retain 24 required enemies, local enemy knowledge, wall-blocked vision and
LOS-required waking. The 1024 branches adjust the normalized clock input to
`ticks / 1024`; batch and rollout sizes remain unchanged. Queue launched at
20:25 ADT on Sep 15; expected total about 14–18 minutes. Queue status is recorded
in `results/vision-budget-comparison-queue-status.json`; runner stops on failure.
Each variant passed smoke and 16,800 CPU/CUDA policy-transition checks; the
1024 variants also explicitly test that tick 512 is nonterminal, tick 1024 times
out, and normalized time resets correctly. The zero-ogre native checks passed
without changing the observation schema. Validation script:
`reviews/vision-budgets/check_suite.py`.

## Why are travel trips short?

Replay of the final 512-turn/two-ogre travel policy reproduced its exact clear
rate across the original 1024 evaluation episodes. For 64,047 selected trips,
mean planned distance was 3.396 steps and mean executed distance was 2.884;
median planned distance was 3, 89.9% were at most 4, and the longest planned route
was 96. Enemy sightings interrupted 21.7% of trips (possibly on arrival).
Vision is a 9×9 window, radius four, further restricted by walls. The nearest
known floor bordering unknown terrain is commonly only a few steps away.
This measurement confirms that short selected routes are the main explanation,
with interruptions reducing their executed length further. Artifact:
`results/vision-frontier-travel-lengths.json`; replay script:
`reviews/vision-budgets/travel_lengths.py`.
