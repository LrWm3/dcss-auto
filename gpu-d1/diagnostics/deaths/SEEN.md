# Seen-floor / death -4 diagnostics at 10M and 30M

Run `gpu-d1/.venv/bin/python gpu-d1/diagnostics/deaths/run_seen.py`.
This evaluates retained seed-0 checkpoints, with no retraining or action
overrides, on the original 1,024 validation episodes (seed 900000, 2048 turns).
Use the original 959-input policy and simulator, including seen-floor count,
+1 kill / +3 clear / -4 death rewards and the same LOS rules.

The shared wall probe now accepts an optional simulator include path; its
default remains the original curriculum simulator. Diagnostic logic is unchanged.
See [method and limitations](WALLS.md) and [fatal-action replay](README.md).
No diagnostic information is supplied to either policy.

## Results, 2026-09-16

| Measure | 10M | 30M |
|---|---:|---:|
| Deaths / 1,024 episodes | 284 | 209 |
| Mean death turn | 217.9 | 192.8 |
| Median death turn | 206 | 160 |
| Mean kills before death | 9.98 | 9.42 |
| Median HP before fatal turn, out of 18 | 2 | 2 |
| At least two adjacent enemies before fatal turn | 71.1% | 77.5% |
| Fatal action was an attack | 80.3% | 85.6% |
| Mean damage taken in final 20 turns | 16.08 | 17.12 |
| Mean neighboring walls at fatal turn, out of eight | 3.75 | 3.66 |
| No empty walkable neighboring tile at fatal turn | 19.7% | 17.2% |
| Crowding-reducing move with an onward neighbor available | 70.4% | 73.2% |
| Alternative crowding-reducing move survives fatal turn | 62.7% | 65.6% |
| Ever without an empty adjacent tile in last 50 turns | 40.8% | 37.3% |
| Entered a local dead end in last 50 turns | 18.0% | 16.3% |
| Used crowding-reducing move when available at low HP, last 50 turns | 37.3% | 31.6% |
| Attacked when crowding-reducing move available at low HP, last 50 turns | 52.8% | 59.7% |

Death percentages describe fatal episodes only. The last two rows are pooled
across qualifying turns in those episodes; low HP is <=4/18. Local dead ends
account for current enemy occupancy, not just terrain. Onward movement checks
hold enemies fixed and may include tiles not known to the policy.

Deaths are fewer, but the remaining ones still commonly involve attacking at
very low HP while crowded. Most fatal states have an empty neighboring tile;
being completely boxed in is not the dominant immediate explanation. Earlier
deaths and less retreat among remaining failures do not establish regression:
the stronger policy changes which episodes enter the death-conditioned sample.
Mean final-20-turn damage of 17.12 exceeds about 4.6 HP of regeneration over
20 turns, consistent with sustained combat overwhelming healing.

The one-turn replays do not prove that 65.6% of deaths were avoidable. Different
actions consume random draws differently; these are hindsight alternatives,
and survival of one turn does not establish escape or an eventual clear.

Both outcome sets exactly reproduce prior clear/death/timeout/turn/kill metrics.
Full state, observation, mask and active output parity passed for 128 steps per
policy; all original fatal actions reproduced death. Geometry unit tests and
neighbor partition checks passed. Evaluation took 27.14 seconds after compilation.
Compact artifact: `results/vision15-seen-death4-death-diagnostics.json`; checkpoint
and source hashes recorded. Numeric traces remain in memory and are discarded.

## Single versus multi-enemy contact

Counts are pre-action states across all episodes, including sleeping enemies.
A contact bout is consecutive turns with at least one enemy adjacent (or visible,
for the visible measure). Any turn with two or more makes that bout multi-enemy.
A one-turn loss of contact splits bouts: these are not necessarily distinct fights.

| Checkpoint / contact | Single-enemy turns | Multi-enemy turns | Multi share of contact turns | Single bouts | Multi bouts | Episodes ever multi |
|---|---:|---:|---:|---:|---:|---:|
| 10M / adjacent | 189,436 | 53,167 | 21.9% | 7,588 | 3,863 | 1023/1024 |
| 10M / visible | 172,013 | 104,073 | 37.7% | 8,892 | 5,651 | 1024/1024 |
| 30M / adjacent | 171,949 | 42,645 | 19.9% | 9,923 | 3,715 | 1020/1024 |
| 30M / visible | 168,919 | 84,153 | 33.3% | 10,658 | 5,712 | 1024/1024 |

At 30M, multi-enemy adjacency occupies 7.67% of all turns but 19.9% of
turns with any adjacent enemy. Multi-enemy contact is nearly universal across
episodes, despite single-enemy states accounting for most contact time.
All earlier diagnostic parity and outcome reproduction checks passed again.
