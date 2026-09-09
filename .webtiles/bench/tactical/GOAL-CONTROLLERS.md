# Goal-controller laboratory v1

This is an isolated replacement for the old `retreat`, `hold`, and committed
`rage_hold` options. It does not change the production RC or historical models.

## What the options do

| Goal | Execution | Reassessment |
| --- | --- | --- |
| Withdraw | Route to recorded entry upstairs, then a rest anchor, then a defensible entry point. Prefer routes avoiding visible enemies. Ascend if appropriate. | Recompute the route each decision; fight adjacent blockers when no unoccupied route remains. After ascent, fight followers and recover. |
| Defend | Choose a nearby known choke/defensible tile, move there, attack without chasing. | At most eight lure waits before abandoning a hold that enemies refuse to approach. |
| Pursue | Approach a reachable visible enemy through known, non-frontier terrain; use adjacent-only autofight to attack. | Reassess on additional threats; at most twelve approach moves, eight tiles from the starting position. Fall back toward known safety when possible. |

Berserk is a separate permission for **each** goal. When permitted, the controller
checks actual ability availability at a close-fighting decision. It does not
activate merely because an enemy is visible, or because an enemy is adjacent
while a withdrawal route remains open. It never changes the navigation goal or
creates a permanent fight commitment. Failed activations have a retry cooldown.

The selector estimates six joint outcome values: three goals × berserk
permitted/not permitted. It selects a pair at encounter entry. The deterministic
controller subsequently decides when that permission applies. **This first
version does not learn turn-by-turn berserk timing or mid-encounter goal switches.**
Those switches are bounded controller rules, logged with reasons.

Emergency resources, confusion, damaging clouds, liquid fire, and adjacent
invisible disturbances use a restricted subset of the existing RC helpers.
This subset cannot auto-explore, descend, pursue via Tab, or independently
activate berserk. Low-HP emergency checks are rate-limited so they cannot
permanently prevent movement when no resource is available.

## Common endpoint and limits

Success requires full HP, no visible hostiles, Crawl reporting safety, no
unresolved invisible-threat evidence, no harmful temporary condition or berserk
recovery, followed by **20 consecutive checked single game turns** with those
conditions remaining true. Damage, danger, or a floor transition resets the
quiet counter. A long macro-wait cannot establish success.

Ascent is not success. Disappearing enemies are not success. Death is negative;
decision/turn budgets and stalls are unresolved. The default limits are 600
decisions, 1500 game turns, eight no-turn actions, or 80 unchanged observations.
No reward is awarded for mere survival until a budget expires.

This is an **observable tactical recovery** criterion, not proof that the area
is permanently safe, that every enemy died, or that the full game progresses.
Withdrawal may leave the original enemy alive downstairs. The old experiment's
floor-change and post-handoff scores are not directly comparable.

## Observation and checkpoint integrity

`goal_env.py` creates separately hashed derived checkpoint bundles. Original
saves and RCs remain unchanged. `goal_bridge.lua` adds only player-known map
cells, a waypoint-relative coordinate frame, existing recovery anchors, threat
memory, and actual Berserk availability. No hidden monsters or unrevealed map
tiles are exposed. A remembered route is not assumed to be currently empty.

Only recorded entry upstairs certify a previously visited destination. A shaft
therefore does not grant an invented upstairs route; an existing rest anchor can
still make withdrawal available. The controller does not exit the dungeon on D:1.
Unavailable goal choices are masked. Opening doors and routing to arbitrary
unrecorded upstairs are intentionally not supported yet.

For each selected case, the runner checks two enhanced resets for equality and
compares the legacy observation projection against an original reset. New
checkpoint metadata does not inherit historical `training_ready` certification.
The checks are recorded separately. Selector training replays also check outcome
agreement with the corresponding collected option trial.

Monster arrays are compared independent of Lua table enumeration order, using
coordinates and name. Pursuit ties are explicitly ordered by coordinates too.
The comparison still checks monster contents and all other observation fields.

The stair adapter queues the normal `<` key. Calling `CMD_GO_UPSTAIRS`
synchronously inside the ready callback starts a stair delay without completing
the input cycle, which caused a live harness lock in the first smoke trial.

## Train and evaluate

```sh
/usr/bin/python3 .webtiles/bench/tactical/run_goals.py \
  --output .webtiles/bench/tactical/artifacts/goals-next-run \
  --jobs 6 --steps 600 --train
```

Omit `--train` and use `--limit 5` for a controller-only pilot. Outputs must be
new directories. The runner uses the hash-pinned dataset and seed partitions in
`options-expanded-v1.json`, but **does not import its old outcome labels**.

Order: validate derived resets; run all six choices on training cases; fit a
linear outcome-value selector from fresh terminal rewards; freeze it; replay
training choices; evaluate the selector and all six controls on validation.
Masked options are not training rows. Validation/test rows cannot enter fitting.
The reserved test split is not executed. This is an encounter-level contextual
bandit/complete-return value fit, not PPO or a neural turn-by-turn policy.

Artifacts include source/engine/dataset hashes, case provenance, full action
observations, reasoned controller events, terminal classifications, model weights,
reset checks, selector-repeat checks, and summaries. Historical artifacts remain
available for audit. An engine failure stops training rather than being labeled
as a character death.

## Verification before fitting

The five-case pilot (`goals-pilot-v2`) completed 30 trials: 25 recovered, five
died, zero stalls or harness errors. Both withdrawal variants recovered on all
five cases. On D:7, withdrawal used 21 movement commands, one ascent to D:6,
then 20 quiet waits. Defense recovered with or without berserk; pursuit died
without berserk and recovered with it. All five derived resets matched their
parent projections and repeated initial observations.

This establishes that the controllers execute and terminate on those examples;
it does not establish that they are optimal. Defensive geometry remains a simple
nearby choke heuristic, unseen opponents remain partially observed, and the
small linear model can still generalize poorly. The six validation cases share
one seed and are not evidence of broad generalization.

The expanded suite has 103 Python tests plus the existing three direct-transport
and ten model-hook Lua checks. Dedicated Lua tests cover invisible probes,
friendly protection, adjacent-only combat, emergency-resource preemption, and
consuming a turn after a rejected ally attack.

## Completed training/evaluation: goals-trained-v3

Fresh collection checked 162 combinations: 136 recoveries, 15 deaths, one
bounded unresolved result, and ten masked choices (152 actual trials). There
was at least one successful available combination for every training case.

| Strategy | Training recoveries | Validation recoveries |
| --- | --- | --- |
| Learned selector | 27/27 | 6/6 |
| Defend, no berserk | 24/27 | 5/6 |
| Defend, berserk permitted | 25/27 | 5/6 |
| Pursue, no berserk | 22/27; one unresolved | 6/6 |
| Pursue, berserk permitted | 22/27 | 6/6 |
| Withdraw, no berserk | 21/22 available; five masked | 6/6 |
| Withdraw, berserk permitted | 22/22 available; five masked | 6/6 |

The selector's 27 engine replays all matched the corresponding collected outcome.
It selected all six goal/permission combinations across training cases. The
previously troublesome main018 gnolls recovered with defense+berserk; the
selector chose that combination and reproduced recovery in139decisions. On the
last validation encounter, both defensive controls died but the selector chose
pursuit without berserk and recovered in57decisions. No model-selected trial
died, stalled, or exhausted its budget. There were no harness errors.

Across collection, selector replays, and validation controls:231recorded rows,
221actual trials,14,241controller decisions. No weights were changed after
validation. Validation comes from just one seed; withdrawal and pursuit controls
also passed allsix, so this does not establish superiority to the best fixed
strategy on unseen seeds. No full-game progression claim is made.

Frozen weights: `models/goal-selector-v1.json` (lab-only; not compatible with the
old production model hook). SHA256:
`1f2b9cf7f525191cb4b2bf0c724bb95efdd43a26cf16db56befb9089d1efb7f0`.
Full artifacts: `artifacts/goals-trained-v3/`; tracked verification evidence:
`evidence/goals-trained-v3.json`.

One conservative availability limitation remains: first-contact checkpoints can
pause immediately after descending, before the old RC updates its entry anchor.
Withdrawal is masked if that anchor is missing, even when the character happens
to stand on usable upstairs. Preserving arrival history at capture time would
recover that option without inventing a route. This was not silently repaired
from hidden engine state or special-cased by seed in the experiment.
