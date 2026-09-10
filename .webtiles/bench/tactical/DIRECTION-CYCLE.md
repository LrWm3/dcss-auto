# Complete directional collection cycle — 2026-09-10

Run: `artifacts/action-direction-cycle-v1`. Parent: `action-direction-v1/capped.pt`.
This repeats the **correction-based imitation** workflow, not RL. No production
deployment, new seed mining, validation-label fitting, or test-set use.

## Results

| Evaluation group | Starting model recovered / died / timed out | Updated model recovered / died / timed out | Teacher |
| --- | --- | --- | --- |
| Original 36 training offsets | 23 / 8 / 5 | 23 / 8 / 5 | 23 / 8 / 5 |
| New 36 training offsets | 29 / 3 / 4 | 29 / 3 / 4 | 29 / 3 / 4 |
| Eight validation variants | 8 / 0 / 0 | 8 / 0 / 0 | 8 / 0 / 0 |

Starting-model original-offset/validation and teacher original-offset/validation
figures are from prior identical-case evaluations; collection supplies the new-offset
starting baseline and the new-offset teacher was replayed here. The updated model
recovered **52/72 training variants and 8/8 validation variants**, preserving
recovery counts and matching the teacher's aggregate counts. This cycle increased
coverage but did **not** demonstrate an outcome gain beyond the starting policy
or pursuit teacher. Equal counts do not imply identical decision traces.

The 3,437 new rows include repeated states, especially healing waits. They contain
858 distinct encoded feature/mask/teacher-label triples, of which **681 were absent
from the parent dataset**. These are representation-level distinctions, not 681
independent encounters or new seeds. The 11 disagreements are corrected action
labels, not 11 independently rescued encounters.

All 3,437 new labels and the exact parent-plus-fresh dataset concatenation passed
independent reconstruction. All 10,115 model decisions in 116 collection/evaluation
episodes matched their saved checkpoints and recorded state/mask inputs. All 224
episode records passed transition/outcome auditing: 118 recoveries, 17 deaths,
17 budget truncations and 72 administrative preflight closes. These pooled counts
span several policies and are not one policy's win rate. No harness errors or
no-turn stalls occurred. 209 Python tests and 13 embedded Lua checks passed.
Zero adjacent-enemy waits and zero waits when the teacher would act were recorded
in collection, updated training replays and validation. Nothing deployed.

## Collection starts the cycle

`run_direction_cycle.py` derives 36 additional training cases: the same 12 training
seeds/checkpoints with **new gameplay RNG offsets 3/4/5**, while preserving offsets
0/1/2 and all eight validation cases. This expands RNG coverage, not the number
of independent seeds or encounter families. Existing cases are never overwritten.
The generator checks parent checkpoint/RC hashes and alters only the named action
RNG hook; regression tests reject missing/duplicate hooks and protect unrelated
augmentation calls.

All 36 new variants passed paired deterministic 16-action preflight prefixes:
72 replays, 1,152 actions, no zero-turn requests. These checks matched initial
observations to the parent cases and repeat trajectories to one another.

The frozen starting model then controls every action on the new training variants.
The unchanged pursuit teacher labels those visited states after collection. All
trajectories are kept, including deaths and budget exhaustion. No teacher takeover.

Collection recovered in **29/36**, with three deaths and four budget truncations.
It generated **3,437 new examples, including 11 teacher disagreements**, with zero
adjacent-enemy waits and zero waits when the teacher would act.

## Fit and evaluation protocol

Append the new arrays to the parent dataset: **12,045 examples**. Verify dataset
hashes and teacher-action availability. Warm-start the existing capped scorer,
then fit exactly ten epochs, batch 128, Adam .001, gradient clipping .5, sampling
seed 43 and the same four-times-uniform probability cap. Budgets and model choice
were recorded before collection. Final training-label accuracy reached 100%; no
checkpoint was selected using validation or an intermediate outcome.

Replay the saved final model on all 72 training variants (original and new reported
separately), pursuit on the 36 new variants, and the model on eight unchanged
validation variants. The collection results are a matched new-offset baseline for
the starting model. Original-offset baseline and validation results come from the
previous identical-case run. Validation remains four families on one studied seed.

The run retains source snapshots, parent/config/case/model/dataset hashes, raw
observations, executed actions, labels, fit history and per-case outcome evidence.
`audit_direction_cycle.py` independently reconstructs the fresh feature/label rows,
checks the aggregate dataset is exactly parent-plus-fresh, and recomputes model
decisions from saved checkpoints and recorded states/masks.

## Reproduce / repeat

Use the existing RL Python environment. The output directory must be new. On a
subsequent cycle, use this cycle as `--parent` and an unused `--rng-start`, e.g. 6.
Requested offsets already present in the parent training config are rejected.

```sh
.webtiles/bench/tactical/.rl-venv/bin/python .webtiles/bench/tactical/run_direction_cycle.py --parent .webtiles/bench/tactical/artifacts/action-direction-v1 --output /absolute/new/cycle --rng-start 3
.webtiles/bench/tactical/.rl-venv/bin/python .webtiles/bench/tactical/audit_direction_cycle.py /absolute/new/cycle
.webtiles/bench/tactical/.rl-venv/bin/python .webtiles/bench/tactical/audit_action_episodes.py /absolute/new/cycle
.webtiles/bench/tactical/.rl-venv/bin/python -m unittest discover -s .webtiles/bench/tactical -p 'test_*.py'
```
