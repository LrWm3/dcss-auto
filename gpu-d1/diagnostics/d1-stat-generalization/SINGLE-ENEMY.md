# Single-enemy danger, healing, and escape

Completed 2026-09-17. No training or checkpoint changes.

Individual enemies can justify avoidance in the existing stat range. The most
difficult confirmed single-enemy encounter has about 8% death risk even at full
player HP. Injured-player risk is much higher. The three tested greedy policies
rest reliably outside combat, but always initially attack in the adjacent cases,
including cases where running to stairs is substantially safer.

## Design

The broad screen covers all 81 combinations of the four combat-stat factors,
all six enemy kinds, and 25/50/100% starting HP, on two held-out map geometries
(seeds 73117 and 73303). Enemy count
is held at the nominal configuration value, but exactly **one enemy is alive**.
The 5832 states include two contexts:

- Sleeping enemy seven tiles away, visible but outside its six-tile wake range.
  Three working stairs are initially visible, each reachable through observed
  floor without entering wake range. The nearest stair takes three moves plus
  descent. Geometry is selected by feasibility before policy evaluation.
- The same player/stair arrangement, with the enemy moved to an adjacent floor
  tile toward its previous position and already awake.

The broad controller screen uses 256 futures per state. The frozen source and
the validation-selected fixed/varied 3M checkpoints each receive 64 futures per
state with greedy actions and their normal partial observations. It evaluates
approximately 4.11 million episodes in 267 seconds, including native compilation
and setup. No bootstrap or training-seed significance claim is made for these
descriptive averages; the broad screen shares random streams across conditions.

A separate confirmation uses 4096 fresh futures per geometry (8192 per table
cell) on nominal and weak-player/strong-enemy profiles, for kinds 3 and 4. It uses
disjoint random streams between states and matching streams between controller
interventions. Confirmation takes 32 seconds, including compilation/setup.

Controllers:

- **Fight:** approach the sleeper, wait for it to become adjacent, then repeatedly
  attack. Once it dies, go to stairs. For adjacent starts, attack immediately.
- **Heal then fight:** use the existing REST macro to reach maximum HP, then the
  fight controller. Available only in the sleeping setup.
- **Bypass:** route to stairs through observed floor, staying outside wake range.
- **Escape adjacent:** route to stairs through observed floor while avoiding the
  enemy's occupied tile. The enemy can pursue and attack normally; success is
  not guaranteed. Used in the focused confirmation only.

The fight controller uses the static distance field to approach the initially
visible sleeper. Escape/bypass pathfinding uses observed floor. Models receive
no controller, global enemy, or route override. All strategies use the existing
combat, regeneration, action masking, LOS, REST, deadline, and stair rules.

Defenses are unchanged: AC 6.81, EV 7.94, SH 9.06, shield block limit 2 per turn,
regeneration 0.23 HP per turn, player hit probability 80%. Enemy kinds 3 and 4
have speeds 10 and 12 respectively, with the same attack-accuracy parameters.
Damage numbers below are uniform raw damage rolls, before player defenses.

## Confirmed combat risk

Enemy kind 3, initially sleeping. Values are **death percentages**:

| Player / enemy stats | Starting HP | Fight | Heal then fight | Bypass |
| --- | ---: | ---: | ---: | ---: |
| Player max18, damage1–4; enemy HP16, damage1–5 | 5/18 | 11.34% | 0.01% | 0% |
| Same nominal stats | 18/18 | 0% | 0% | 0% |
| Player max12, damage1–3; enemy HP20, damage1–6 | 3/12 | 58.76% | 7.34% | 0% |
| Same hard stats | 6/12 | 32.51% | 7.79% | 0% |
| Same hard stats | 12/12 | 7.78% | 7.78% | 0% |

For the hard full-health case, the 95% Wilson interval is 7.22–8.38%.
Zero observed deaths in 8192 rolls is not proof of zero underlying risk; its
two-sided Wilson upper bound is approximately 0.047%.

With that hard enemy **already adjacent**:

| Starting HP | Fight deaths | Escape-to-stairs deaths |
| --- | ---: | ---: |
| 3/12 | 71.84% | 5.63% |
| 6/12 | 40.43% | 0% |
| 12/12 | 7.42% | 0% |

At 3/12 HP the individual 95% intervals are 70.85–72.80% for fighting and
5.15–6.15% for escaping. This is a practically large, verified avoidable risk.
The faster kind 4 shows the same qualitative pattern: 67.09% fighting deaths
versus 4.50% escaping at 3/12 HP, and 5.48% fighting deaths at full HP.

Across the entire grid, full-health fight deaths average only 0.127% in the
sleeping context and 0.104% in the adjacent context. Danger is concentrated in
the weaker-player/stronger-enemy combinations, and especially low current HP.
At 25% starting HP those averages rise to 6.59% and 10.04%. Most isolated fights
are relatively safe, which helps explain why ordinary episodes may provide a
weak signal for learning strength-dependent avoidance.

## Model behavior

All three models select REST initially in **every** sleeping, injured starting
state (1944 states per model). At full HP they move. Thus they already possess
the basic heal-before-engagement behavior under these conditions.

All three initially ATTACK in **every adjacent state** (2916 per model), across
the full player/enemy stat range and all three HP levels. Their adjacent rollout
results are identical in the broad evaluation: average death rates 9.98%, 1.95%,
and 0.10% at 25/50/100% starting HP. They do not select the verified escape first
action even in the confirmed high-risk cases.

In sleeping scenes, average model death percentages at 25/50/100% HP are:

| Model | 25% HP | 50% HP | Full HP |
| --- | ---: | ---: | ---: |
| Frozen source | 0.077% | 0.076% | 0.071% |
| Fixed-stat continuation | 0.061% | 0.069% | 0.058% |
| Varied-stat continuation | 0.016% | 0.021% | 0.023% |

The varied model has favorable point estimates in this very narrow layout
comparison. This does not establish general superiority: only two geometries
are used, the events are rare, and these are post-training diagnostics.

Changing only player damage across 1728 matched groups changes the initial
greedy choice in zero groups for source/varied and one for fixed. This tests
first choices, not every later action or the complete probability distribution.

## Interpretation and limits

There is enough single-enemy danger in the existing stats to reward learning
avoidance. We do not need stronger enemies merely to demonstrate an avoidable
single-enemy death. The near-universal initial attack under adjacency remains
a measurable behavioral limitation.

However, these layouts deliberately provide a short safe exit. With +1 for
descending, no kill reward/XP, and a small turn cost, bypassing is better even
when the player is strong. These tests establish danger and a missing escape
response; they do **not** demonstrate a situation where optimal strategy flips
from avoidance to fighting as power increases. That requires a cost to the
detour, an enemy obstructing the objective, or another reason fighting helps.

The two map geometries are not independent evidence from many layouts. The
reported confirmation intervals describe combat-roll uncertainty conditional
on these fixed scenarios, not generalization or training-seed uncertainty.
Initial enemy energy is fixed at 70; this screen does not sweep energy phase.

## Reproduction and artifacts

Run from the repository root:

```sh
gpu-d1/.venv/bin/python gpu-d1/diagnostics/d1-stat-generalization/single_enemy.py
gpu-d1/.venv/bin/python gpu-d1/diagnostics/d1-stat-generalization/single_enemy_summary.py
gpu-d1/.venv/bin/python gpu-d1/diagnostics/d1-stat-generalization/single_enemy_confirm.py
```

The isolated diagnostic library is built under the ignored
`gpu-d1/learning-runs/d1-stat-generalization/single-enemy/` directory. Production
simulator sources and training artifacts are unchanged. Assertions check enemy
count/visibility/HP, REST legality/completion, terminal outcomes, and that all
sleeping bypass trials exit without kills, damage, or waking the enemy.

Compact tracked results: `gpu-d1/results/d1-single-enemy-danger.json` and
`gpu-d1/results/d1-single-enemy-confirmation.json`. The 11MB raw broad report
stays in the ignored run directory. In raw diagnostic metrics, HP-on-first-attack
and HP-after-kill use -1 when that event never occurs; their unconditional means
must not be interpreted as conditional survivor HP.
