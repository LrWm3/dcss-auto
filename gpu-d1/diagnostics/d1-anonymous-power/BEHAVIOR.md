# What the anonymous-power policy learned

Post-training diagnostics, 2026-09-17. No new training or production-policy
changes. Runtime 143.7 seconds. Compare source, 500,224 and 5,000,192 decisions.

## Matched encounters

864 states: four held-out map geometries, sleeping-at-distance versus adjacent
awake enemy, nine player profiles, half/full HP, six enemy templates. Three
nearby visible stairs provide an alternative to fighting. Geometry selection
uses placement feasibility, not policy outcomes. Each policy/mode gets 32 combat
futures per state. These are repeated outcomes on four geometries, not thousands
of independent layouts. Greedy uses the actual type-first policy decision rule.

| Starting encounter | Source greedy exits | 500k greedy exits | 5M greedy exits | Source sampled exits | 5M sampled exits |
| --- | ---: | ---: | ---: | ---: | ---: |
| Sleeping enemy, safe stair route | 78.12% | 87.83% | 99.07% | 79.19% | 99.55% |
| Adjacent awake enemy | 66.69% | 66.69% | 86.92% | 66.70% | 88.31% |

In sleeping encounters, source greedy exits without killing in 50% of all
trials; 5M does so in 99.07%. In adjacent encounters, the corresponding numbers
are 0% and 32.94%. Aggregate initial MOVE probability rises from approximately
zero to 27.6% during adjacency; most movement probability (24.9 percentage
points) is in the stair-guide direction. This supports learning useful bypass
and escape behavior, rather than only delaying combat.

### Causal sensitivity to stats

Matched observations and action masks are identical except the relevant stats.
At fixed full-HP fraction, player-profile changes alter only the three new
player stat fields. Enemy damage-only pairs change exactly column 1019.

For adjacent enemies, changing only damage cap:

- Enemy HP6, damage4 to20: mean initial MOVE probability increases **17.13pp**.
- Enemy HP24, damage10 to20: mean initial MOVE probability increases **34.87pp**.

These average across player profiles, HP fractions, and geometries. Source
responses to both changes are exactly zero; the 500k response is negligible.

The 5M policy also responds to its own power. Averaging enemy templates and
geometries, initial MOVE probability for the weakest versus strongest player is
**51.7% versus38.9% at half HP**, and **12.6% versus7.3% at full HP**. Increasing
player damage while holding maximum/current HP fixed reduces MOVE probability
in each of the six HP-level groups in this probe.

Thus the policy uses relative-power inputs in a sensible direction. This does
not establish calibrated danger estimates or an optimal fight/avoid rule:
with nearby safe stairs, bypassing is worthwhile even when fighting is safe.

## Why ordinary-floor greedy evaluation remains poor

Exactly reproduced the existing seen-stat greedy test: 1800 episodes,
264 exits, 983 deaths, 553 timeouts. Of the 553 timeouts, **259 (46.8%)** contain
at least64 consecutive WAIT decisions. Across all timeout episodes, mean WAIT
count is885.8, including882.0 waits at full HP with no awake enemy visible.
This accounts for a substantial part of the timeouts, not all of them.

Captured the first three 64-WAIT states per player profile (27 total).
Every captured state has full player HP, exactly one visible sleeping enemy,
no visible awake enemy, no adjacent attack available, and no known stairs.
Continue each identical state with128 fresh simulator futures:

| Policy/intervention | Exit | Death | Timeout |
| --- | ---: | ---: | ---: |
| Source greedy | 33.51% | 62.79% | 3.70% |
| 5M greedy | 0% | 0% | 100% |
| 5M sampled | 29.43% | 48.93% | 21.64% |
| 5M greedy, disallow idle WAIT | 9.92% | 10.45% | 79.63% |

The last intervention masks WAIT only at full HP with no awake enemy visible
and another legal action available. It does not force navigation or attacks.
It is an evaluation intervention, not a proposed general rule: waiting can
have valid tactical uses elsewhere. The remaining timeouts show removing this
one action does not provide a reliable alternative route. Their detailed
movement failure mode was not classified in this diagnostic.

These states were selected for stalling and are not representative of all
floor failures. Continuations preserve the remaining deadline, but reseed future
randomness. The source's successes show at least some stalls are recoverable;
they do not prove all original deaths were avoidable.

## Interpretation

The 5M policy learned both stat-sensitive decisions and useful local escape
behavior. That has not translated into reliable overall improvement: the
previous held-out seen-stat sampled exit rate moved only23.28% to24.28%, while
greedy fell22.78% to14.67%. A concrete obstacle is what to do when avoiding a
sleeping threat while the exit is still undiscovered. This is consistent with
learning avoidance before learning how to continue navigating around danger.
It is not proof that the reward, architecture, or optimizer alone caused it.

A next bounded experiment would supply matched practice where stairs are
initially unknown and a sleeping threat lies near the exploration route, with
a known feasible alternative path. Keep the current checkpoints as controls;
measure successful discovery/exit and stalling, not merely reduced fighting.

## Reproduce

```sh
gpu-d1/.venv/bin/python gpu-d1/diagnostics/d1-anonymous-power/behavior.py
gpu-d1/.venv/bin/python gpu-d1/diagnostics/d1-anonymous-power/summarize_behavior.py
```

Raw trajectories/snapshots remain under ignored
`learning-runs/d1-anonymous-power/behavior/`. Compact measured results are in
`results/d1-anonymous-power-behavior.json`. One training seed; four matched
geometries; no claim of general statistical reliability from this probe alone.
