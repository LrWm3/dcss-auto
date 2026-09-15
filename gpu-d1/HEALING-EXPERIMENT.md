# Limited full-heal resource, multi-layout floor clearing

Four independent fresh seed-0 models train to 30M decisions each, sequentially:
`route_heal0`, `route_heal1`, `route_heal2`, `route_heal4`. The initial charge
count is fixed per run and replenished at each episode reset. The build supports
0 through 7 charges. This is 120M total decisions, rounded to full PPO updates.

All use 40 enemies, sleep on, 1024 turns, 256 training layouts, 32 validation
layouts × 32 episodes, the corrected ring/frontier/route observations and
two 128-unit hidden layers. No awake inputs or frame stack are added.

The tenth action (index 9) consumes one charge and restores HP to full before
the normal regeneration and monster phase. It takes one ordinary turn. Healing
does not prevent monsters from attacking or killing the player that turn.
The action is masked at full HP, zero HP, or zero charges. An externally forced
invalid heal behaves as a wait without charging a use penalty. Input 421
(zero-based) is remaining charges divided by 7; total input width is 422.
The zero-charge control has identical model dimensions, with heal always masked.

Each successful use costs -0.05, in addition to -0.001 for the turn. Other
rewards retain the original +1 per kill, +3 per clear, -1 per death and +0.002
per newly seen floor tile. The scaled-clear experiment's +10 is not included.

Report sampled and greedy clears, kills, deaths and timeouts at 0/1M/3M/10M/30M,
plus training time. Per-map and aggregate diagnostics include average heals
used per episode, mean HP before a heal, mean HP restored per heal, charges
remaining at death, and fraction of deaths with unused charges. HP summaries
are weighted by heal events; death summaries condition on deaths and use null
when there are none. Terminal counters are captured before auto-reset.

This tests learning to use additional survival resources in a modified task.
An improvement does not establish avoidability of deaths in the original task.
All conditions have the same network initialization seed and dimensions;
their trajectories diverge as resource inputs and actions differ. Repeat seeds
before declaring reliable gains.

```sh
gpu-d1/.venv/bin/python -u gpu-d1/scripts/run_ring_ablations.py \
  --variants route_heal0,route_heal1,route_heal2,route_heal4 \
  --seeds 0 --steps 30000000 \
  --output gpu-d1/learning-runs/route-healing-30m
```

The existing disk limits apply: 2 GiB suite budget, 5 GiB free reserve, latest
and best checkpoints only per run. Checkpoints include resource state and can
resume exactly. Previous completed experiments remain in their own folders.

Verification includes full-heal/empty/full-HP masks, charge consumption, reward,
normal monster action after healing, charge observation, terminal diagnostics,
auto-reset, CPU/CUDA trajectory parity, smoke training of all four conditions
and original route control, and interrupted-resume equivalence.

## Pending follow-up: forced-healing policy (do not run yet)

User requested recording this comparison only; it is not launched or queued.
Compare learned healing against a fixed HP-threshold rule using the same saved
movement/combat policy, layouts, episode seeds and initial charge counts.
When HP is at or below the chosen threshold and a charge is available, force
the heal action. Otherwise mask healing and sample from the policy's remaining
actions. This replaces its healing decisions with the rule while retaining
learned movement/combat. Keep the one-turn cost and -0.05 use penalty unchanged.

Predeclare a small threshold sweep (for example 4, 6, 8 and 10 HP out of 18)
before running. Evaluate the unchanged learned policy on the same episode bank
as the reference. Report clears/deaths/timeouts, charges used, HP at use and
unused charges at death for 1, 2 and 4 starting charges. Select thresholds on
validation only; do not use the reserved test split for tuning.

This is an inference-time intervention on policies trained with learned healing,
so changed state distributions can affect performance. It is not equivalent to
training movement/combat with the forced rule from the outset. A favorable
result would motivate that separate training comparison later.
