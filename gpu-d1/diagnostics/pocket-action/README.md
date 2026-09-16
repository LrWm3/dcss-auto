# Static pocket action symmetry

The policies are directionally inconsistent before any enemy moves. This isolates
an immediate policy response from movement tiebreaks and differing combat histories.
It does not establish the training cause, or explain the entire earlier rollout gap.

## Method

Run `gpu-d1/.venv/bin/python gpu-d1/diagnostics/pocket-action/run.py` from repository root.
No training, rollout transitions, action sampling, or checkpoint changes occur.
The diagnostic uses the unchanged native simulator observation and action-mask code.

Use the prior six-step pocket geometry, but start the player inside the protected
pocket at fixed absolute coordinates (40,35), with one awake adjacent enemy at its
only walkable neighbor. All local terrain is remembered, including the room beyond
current vision; disconnected reset padding is unknown. This controlled knowledge
state eliminates frontier tiebreaks. Native current LOS remains in the observation.
The player has 256 elapsed turns, and 23 enemies are marked killed. Neither the
remaining count nor enemy energy is an explicit observation feature in these models.
The only legal actions are attack and wait. The diagnostic does not claim this
remembered state is the same as any earlier six-enemy rollout state.

Sweep all six ordinary enemy kinds, player HP 6/12/18, enemy HP full/half/1,
four rotations, and both reflections: 432 constructed observations per policy.
These are deterministic probability queries, not 432 independent sampled episodes.
Use the existing original and clump-trained seed-0 30M checkpoints.

Checks pass for exactly one visible enemy, two legal actions, zero frontier cues,
fixed player position, and equality of all 959 observation features with the
appropriately transformed reference (absolute tolerance 1e-7). The checks rotate
terrain, visibility, enemy grid, ring memory, and enemy relative coordinates while
holding scalar features fixed. Thus native LOS or frontier selection cannot be
responsible for an unmatched input feature in this test.

## Results

Probability of waiting with player HP 12/18 and one full-health kind-3 enemy
(16 HP, speed 10, damage 5), before any simulation step:

| Pocket direction | Adjacent enemy direction | Original | Clump-trained |
|---|---|---:|---:|
| SE | NW | 0.308% | 5.434% |
| SW | NE | 0.003% | 5.858% |
| NW | SE | 39.056% | 1.243% |
| NE | SW | 0.150% | 40.275% |

Both policies' most likely action is still attack in these four particular states.
Sampling would nevertheless wait very frequently in their problematic orientation.
Mirrored cases yield identical probabilities at matched pocket compass directions
in this setup; they are not extra independent evidence.

Across the 54 enemy-kind/player-HP/enemy-HP combinations per orientation:

| Pocket direction | Original mean wait | Clump-trained mean wait |
|---|---:|---:|
| SE | 1.53% | 4.88% |
| SW | 0.042% | 7.49% |
| NW | 51.72% | 1.17% |
| NE | 0.34% | 27.79% |

Original NW wait probabilities span 32.5–76.0%; wait is the greedy action in
27/54 states. Clump-trained NE spans 12.5–50.4%, with greedy wait in 1/54.
The troublesome directions match the earlier six-enemy pocket rollouts.

This demonstrates a policy-level rotation inconsistency in a synthetic test.
It does not prove that every wait is harmful (the simulator regenerates health),
or measure performance on ordinary maps. Simulator asymmetries during training
could still contribute to how these direction-specific responses were learned.

Full probabilities, checkpoint hashes, source hashes and checks are in
`gpu-d1/results/pocket-static-actions.json`. Runtime: approximately 14 seconds,
including map construction, two native compilations, and policy evaluation.
