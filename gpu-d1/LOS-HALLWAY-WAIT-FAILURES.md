# Remaining deaths with waiting and hallway retreat

Audits the **privileged pursuit + observed hallway retreat + awake-enemy waiting + rest** arm of `results/los-hallway-wait-awake.json`. The LOS-only arm is not audited here. No policy behavior was changed.

## Full-panel facts

There are 24 deaths among 1,024 episodes. 22 occur within 34 physical turns; the other two at 96 and 123 turns. 23 of the 24 never initiate hallway retreat. Only episode 997 retreats, reaching its destination before later dying in combat.

## Six deliberately selected examples

These cover opening crowds, a new death after adding waiting, and both later deaths. This is not a random sample for estimating causes across the full panel.

| Episode | Death turn / kills | What happens | A tested alternative that clears all 24 enemies |
|---|---|---|---|
| 624 | 10 / 1 | Six initially visible sleepers wake and converge; up to six enemies adjacent. No known exact hallway. The first eastward move leaves an enemy adjacent immediately, so approach-waiting never activates. | First action northwest instead of east; full clear at turn 513. |
| 135 | 20 / 2 | Up to five adjacent enemies in an opening crowd, no known exact hallway; attacks until dead. | At decision 11, 8 HP, northeast instead of attacking northwest; clear at turn 426. |
| 386 | 29 / 3 | Survives an initial multi-enemy fight at 2 HP, then advances west toward a visible sleeping enemy. That wakes it; waiting only restores HP to 3 before adjacency. Dies in the next fight. Rest-to-full is unavailable while the sleeper is visible. | At that exact 2-HP decision (21), east instead of west; clear at turn 440. One wait at that point still dies. |
| 787 | 34 / 5 | Opening crowd reaches seven adjacent enemies; no known exact hallway and no approach waits. | First action north instead of east; clear at turn 363. |
| 997 | 123 / 7 | Retreats eight steps, arrives at full HP, but encounters a third enemy approaching from the other side. Eventually fights enemies immediately east and west in the hallway. No second retreat while the encounter remains visible. | At decision 96, 14 HP, attack west instead of east once; clear at turn 484. |
| 1008 | 96 / 7 | Waits for two strong enemies, then fights both simultaneously at full HP. No known exact hallway; continues attacking as health collapses. | At decision 79, 6 HP, east instead of attacking west; clear at turn 549. |

The five sampled episodes that never retreat have zero known exact hallway candidates whenever the retreat trigger is checked. Their issue is not the first-step-away rejection seen in some previous failures.

Episode 997 illustrates that a two-ended corridor allows **two** attackers when enemies approach from opposite ends. At decision 92, a sleeping third enemy appears west of the destination; by decision 93 it is awake. By decision 96 enemies are adjacent on both sides. The policy attacks the east enemy (10 HP) rather than the west enemy (also 10 HP); overriding that tie once changes the eventual outcome. This is evidence that the loss was not forced by that exact state, but not evidence that west is generally the better target.

## What “avoidable” means in this audit

For each episode we saved the exact simulator state, including RNG, observation, terrain memory and retreat state at several moments: initial decision, first multiple-awake sighting, first multiple-adjacent encounter, first HP <=9, and (when present) a low-HP sleeping-only sighting. We tried every legal single-action replacement at each saved moment, then resumed the unchanged policy. Rest was never allowed outside its actual mask.

**All six episodes have at least one alternative producing a full clear.** Every unchanged continuation reproduced the original terminal outcome, kills and physical turn count. We tested 222 continuations including unchanged controls and repetitions of the original action. All actions passed the legal mask, all continuations terminated, and simulator worlds retained their original RNG state when copied into evaluation lanes.

This is hindsight search, not a deployable improved policy. Changing actions changes subsequent combat RNG consumption, positioning and timing together. A winning continuation establishes existence under that exact saved state; it does not establish a reliably higher survival probability over fresh randomness, or a rule the agent can identify from its observation. These results must not be reported as a general clear-rate improvement.

For episodes 624 and 787, none of the tested single-action replacements at the first half-HP moment rescued the episode. Their successful alternatives acted earlier. Failure of this limited search does not prove those later states are unwinnable; multi-action escape sequences were not searched.

## Implications

Remaining behavior gaps include:

- Opening positioning around nearby sleeping groups: the current rule only reacts once enemies are awake, often after one has already reached adjacency.
- Low-HP caution around sleeping enemies: waiting for awake foes does not stop approaching a sleeper at 2 HP, and the rest macro is unavailable while that sleeper is visible.
- Defensive position quality: an exact hallway is not safe from both directions, and the committed retreat does not reassess that risk.
- Combat target choice and disengagement: lowest-HP targeting and continued attacks are fallible; successful alternatives exist, but their general reliability needs a separate test.

## Reproduction and artifacts

```sh
gpu-d1/.venv/bin/python gpu-d1/diagnostics/seek-destroy-los/inspect_failures.py --wait-for-awake
gpu-d1/.venv/bin/python gpu-d1/diagnostics/seek-destroy-los/counterfactual_wait.py
```

- `results/los-hallway-wait-failure-traces.json`: both waiting-policy arms for six selected episodes, including visible maps, health, enemies, actions and hallway diagnostics.
- `results/los-hallway-wait-counterfactual.json`: all tested alternatives and terminal outcomes for the retreat arm.
