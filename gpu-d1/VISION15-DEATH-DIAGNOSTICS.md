# What kills the current no-travel policies?

2026-09-15. Three 10M policies, 1,024 validation episodes each, 2048-turn limit. No retraining. Same sampled evaluations as the preceding comparison, reproduced exactly. See [diagnostic definitions and limitations](diagnostics/deaths/README.md).

| Measure | Fixed 512 | Curriculum | Fixed 2048 |
|---|---:|---:|---:|
| Deaths | 334 | 333 | 383 |
| Mean turn of death | 199.6 | 186.4 | 177.9 |
| Mean kills before death | 9.7 | 9.1 | 8.9 |
| Deaths starting fatal turn with 2+ adjacent enemies | 80.8% | 81.7% | 82.8% |
| Deaths with 2+ adjacent enemies during last 20 turns | 98.2% | 95.5% | 94.8% |
| Fatal action was attack | 86.5% | 83.5% | 86.7% |
| Damage in deaths on turns starting with 2+ adjacent enemies | 69.5% | 70.4% | 71.1% |
| Alternative action survives fatal turn | 93.7% | 95.5% | 94.0% |
| Alternative empty-floor move survives fatal turn | 81.7% | 81.7% | 80.2% |
| Move reducing initial adjacency survives fatal turn | 78.4% | 78.4% | 75.7% |
| Mean damage in final 20 turns | 16.4 | 17.1 | 16.4 |
| Median HP before fatal turn | 2 | 2 | 2 |

## Assessment

The dominant observed pattern is sustained combat against multiple adjacent enemies, followed by continuing to attack at very low health. All three schedules show it. Deaths happen well before the deadline and after roughly nine kills. Crowding is therefore a better immediate investigation target than additional exploration time.

Full health is 18 HP, and regeneration progresses at 0.23 HP per turn. Fatal episodes take about 16–17 damage in their last 20 turns, while regeneration can restore only about 4–5 HP over that window. Median HP before the fatal action is 2. This is consistent with damage overwhelming healing during crowded fights. It does not isolate whether poor positioning, target selection, enemy strength, or combat randomness created the situation.

In death episodes, around 23–26% of all turns start with multiple adjacent enemies; for the fixed-512 and curriculum successful episodes it is about 9–10%. These are duration-dependent associations, not randomized causal comparisons. Successful episodes take more total damage (about 58–59 versus 42–43 for those two policies), but survive much longer, allowing more recovery. Total damage alone is consequently a poor measure of combat competence.

Counterfactual replay establishes only immediate alternatives. Many fatal states admit a legal movement action that reduces initial crowding and survives the next turn. It does not show that pursuit can be escaped or the floor cleared. Different actions consume the same initial RNG stream differently, and selecting the best outcome uses hindsight. It would be incorrect to call this the percentage of avoidable episode deaths.

The next causal experiment should branch earlier in dangerous encounters and compare the unchanged policy against a simple low-health disengagement controller over the rest of the episode. Track survival, clears, renewed contact and recovery; merely delaying the final blow is insufficient. No such controller was applied here.

## Validation and artifacts

The extension includes unchanged simulator source. Full state, observations, masks and active outputs match ordinary stepping for the first 128 steps of each policy. All final clear, death, timeout, kill and turn metrics match the existing baselines exactly. Every original fatal action reproduces death from its saved state. Source and checkpoint hashes are recorded. No training or test-set evaluation was performed.

Results: `results/vision15-death-diagnostics.json`; executable: `diagnostics/deaths/run.py`. Runtime logs and compiled libraries are ignored; in-memory traces are discarded.
