# Tactical scenario recheck after navigation-only anchoring

The 30M policy retains healing and protected-position combat, but does not
choose the retreats that make these constructed encounters much safer. This
failure was already present in its imitation initialization. Stable ordinary-map
clear rates do not imply that the earlier tactical problems have all been solved.

No training or checkpoint modifications were performed. Compare original
imitation, navigation-only anchor at 10M, and its 30M continuation, seed 0.
Use the current 999-input, 18-action native simulator: MOVE 0–7, ATTACK 8–15,
WAIT 16, REST 17. The policy chooses action type before direction. REST is
available below full HP whenever no awake enemy is visible. All enemy sleep
information remains visibility-gated; observation, movement and combat code are
unchanged. The older fixture constructors and geometries are reused, with their
scripted action encodings translated to the current interface. Old nine-action
checkpoint scores are not directly comparable across these simulator versions.

## Retreat and protected combat

Each geometry sweeps weak/tough enemy groups, HP 6/12/18, four rotations and
64 combat RNG seeds per condition: 1,536 episodes per policy/mode. Combat seeds
repeat across rotations and conditions, so these are not 1,536 independent
training or scenario seeds. Six-enemy pockets at distances 2, 4 and 6 are visible
at the start. The distance-6 geometry is also reflected. Diagnostic rollouts stop
after 256 decisions; every 30M greedy episode resolved as a clear or death.

Greedy clear rates, averaged equally over these conditions:

| Geometry | Initial imitation | 10M | 30M | 30M, forced retreat route only |
|---|---:|---:|---:|---:|
| Three adjacent foes, one step into hallway | 63.54% | 63.54% | 63.54% | 93.23% |
| Six foes, three steps into hallway | 36.46% | 44.27% | 41.86% | 88.35% |
| Two-step diagonal pocket | 36.98% | 44.86% | 40.69% | 88.80% |
| Four-step diagonal pocket | 29.56% | 30.14% | 29.30% | 86.78% |
| Six-step diagonal pocket | 28.58% | 30.01% | 30.14% | 87.43% |
| Six-step pocket, reflected | 29.69% | 28.91% | 31.64% | 86.39% |

None of the three unmodified policies reached the protected square in any of
these sampled or greedy rollouts. At 30M, the initial probability of taking the
first retreat step is below 0.0001% in every condition. Forcing only the first
1/2/3/4/6 retreat moves, then returning control entirely to the greedy policy,
produces the rightmost column. Its resulting clear rates equal the scripted
retreat-then-weakest-adjacent-attack control on these cases. This establishes a
large avoidable performance gap in the tested states, not that every death can
be avoided.

Neither imitation nor 30M ever greedily waited with an adjacent enemy after
being routed into the pocket/hallway. This includes the multi-enemy encounters.
In contrast, the sampled policy is still weak when it must find the route itself:
30M sampled clears are 60.61%, 37.83%, 37.57%, 14.52%, 20.96%, and 22.85% in the
same row order. PPO has not produced a general tactical improvement here.

## The old direction-dependent waiting behavior

Repeat the static protected-pocket test: one adjacent enemy, remembered local
terrain, zero frontier cue, exactly ATTACK and WAIT legal. Sweep six enemy kinds,
HP 6/12/18, enemy HP full/half/one, four rotations and both reflections: 432 states.

| Policy | Mean WAIT probability | Maximum WAIT probability | Greedy WAIT states |
|---|---:|---:|---:|
| Initial imitation | 0.03194% | 0.03777% | 0/432 |
| 10M | 0.08951% | 0.13840% | 0/432 |
| 30M | 0.00083% | 0.00159% | 0/432 |

WAIT probabilities across corresponding native rotations/reflections agree to
within 0.000002 absolute probability. The earlier large direction-specific WAIT
response does not recur in these current policies. This is consistent with the
D4-averaged architecture; it does not imply that native trajectories are exactly
rotation-invariant, since enemy movement and tie-breaking can differ.

## Healing before waking a sleeping enemy

Use the earlier open-room fixtures, three initial geometries (off-axis just
outside wake range, visible at the vision edge, and outside vision), HP 2/9/18,
and two enemy difficulties. Each condition has 32 combat seeds across eight
orientations. These repeat seeds; this is a diagnostic sweep, not a training-seed
significance test. The current physical-turn deadline is 2,048, and sleeping
visible enemies permit REST. The old rest experiment's availability rule differed.

All three checkpoints greedily rested before waking the enemy in every low/half
HP episode, reaching HP 18 at wake. At full HP, REST was correctly unavailable.
At 30M, sampled rest-before-wake was 99.97% across low/half HP cases; mean HP at
wake was 17.997. Hidden enemies had zero enemy observation fields, and initial
visible enemies had the expected asleep status. No healing probe timed out.

Representative low-HP (2/18), visible-at-edge results:

| Enemy | Engage immediately | Scripted heal first | Imitation greedy | 30M greedy |
|---|---:|---:|---:|---:|
| Reference, kind 3 with 28 HP | 40.63% | 100% | 100% | 100% |
| Hard, kind 4 with 48 HP | 9.38% | 96.88% | 93.75% | 93.75% |

Across all healing conditions, greedy clears are identical for imitation, 10M
and 30M: 97.09%. The remaining hard-enemy losses concern post-healing combat,
not a failure to heal first. The scripted heal-first control uses WAIT until
full; a REST-first control obtains the same aggregate result.

## Interpretation and artifacts

The current imitation teacher attacks adjacent foes, rests safely, and waits for
visible awake foes to approach; it does not teach a retreat-to-cover strategy.
The observed near-zero retreat probability suggests PPO gets very little
experience of that alternative. These evaluations show the missing behavior,
but do not separately establish how much is due to initialization, exploration,
reward/credit assignment, or the continued policy anchor. The anchor is disabled
when an awake enemy is visible; these initial retreat decisions are therefore
not directly penalized by the auxiliary anchor on those observations.

The useful next distinction is learning **where to fight** versus executing
combat once already in a good position. The latter is strong in this sweep;
the former remains absent. Healing and directional consistency were already
present at imitation initialization, so they are not newly learned 30M gains.

Run with `gpu-d1/.venv/bin/python`:
- `diagnostics/autoregressive-imitation/scenario_recheck.py`
- `diagnostics/autoregressive-imitation/scenario_healing.py`

Results: `results/autoregressive-scenario-recheck.json` and
`results/autoregressive-scenario-healing.json`, including checkpoint/native
hashes and condition-level outcomes. Generated CUDA sources, binaries and other
build artifacts live in ignored directories. Runtime was 61.1 seconds for
retreat/static tests and 11.9 seconds for healing, including native compilation.
