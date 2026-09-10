# Pursuit imitation and RL fine-tuning — 2026-09-10

Run: `artifacts/action-imitation-v1`. Config and cases unchanged from
`artifacts/action-pilot-v2/config.json`; see `ACTION-RL.md` for the ten-action
interface, recovery definition, limited observation history and conservative masks.
Production RC/model untouched. No test cases loaded.

## Results

| Frozen policy | Training recovered / died / timed out | Validation recovered / died / timed out |
| --- | --- | --- |
| Scripted pursuit teacher | 15 / 2 / 1 | 8 / 0 / 0 (previous identical-case run) |
| Imitation only | 13 / 3 / 2 | 4 / 3 / 1 |
| Imitation + PPO | 6 / 10 / 2 | 3 / 3 / 2 |
| Previous random-initialized PPO | Not replayed here | 3 / 4 / 1 |

Imitation is a modest improvement in validation recovery count over the previous
random-initialized PPO, but this tiny correlated sample cannot establish a reliable
gain. It remains below the teacher. **PPO fine-tuning degraded the imitation
checkpoint**, including on fixed in-sample training replays. No model was deployed.

Imitation failed both ribbon-worm validation offsets after waiting beside an
adjacent visible enemy for 37 and 51 turns, respectively. The failed adder offset
also included five waits beside an adjacent enemy. The fine-tuned policy continued
to wait extensively. Neither model used berserk in deterministic validation.
High overall demonstration accuracy therefore did not solve closed-loop combat.

All **153 recorded episodes** passed transition/mask/reward/outcome audits: 82
recoveries, 52 deaths, 13 budget truncations and six administrative closes across
demonstration collection, stochastic training and frozen evaluations. No harness
errors or no-turn stalls occurred. The full suite passed 197 Python tests plus
13 embedded Lua checks. These pooled audit counts are not policy performance rates.

The evidence suggests prioritizing combat-state imitation and training-time
on-policy correction: reduce the dominance of repeated safe healing waits, collect
teacher labels at states reached by the learner on **training seeds only**, and
measure directional/combat accuracy separately. Before another PPO experiment,
require reliable training-rollout imitation and consider an imitation/KL constraint
to limit drift. These are proposed experiments, not fixes proven by this run.
Do not choose variants or checkpoints by repeatedly optimizing these validation cases.

## Fixed experiment

`train_action_imitation.py` collects one action-matched pursuit-without-berserk
demonstration from each of the 18 training variants (six seeds, three RNG offsets).
All trajectories are kept, including deaths and budget exhaustion; this imitates
the teacher, not an oracle. Demonstration episodes pass the existing transition
auditor and the encoded arrays have recorded checksums and training provenance.

The teacher generated 1,178 actions: 1,008 waits and 170 directional moves/attacks.
Outcomes: 15 recovered, two died, one exhausted 192 requests. The labels contain
no berserk examples. Consequently imitation alone cannot be expected to learn
when berserk helps; subsequent RL must explore that action.

Fit the same [128,128] masked actor network for **20 epochs**, batch 128,
Adam learning rate .0003, gradient clipping .5, seed 42, unweighted masked
negative log likelihood. This updates the actor; the separate critic remains
randomly initialized. PPO uses its fresh optimizer after imitation.

Save the final imitation checkpoint, then perform exactly **6,144 PPO actions**
with the earlier pilot's hyperparameters and six workers. Save the final RL
checkpoint. Both budgets were recorded before collection/training. Neither model
is selected using validation; all evaluations happen after both fits finish.

Evaluate both frozen checkpoints deterministically with masks on all 18 training
variants and the same eight validation variants (four families, one seed, two RNG
offsets each). These validation cases were studied previously, so this is a small
development comparison, not a final generalization claim. Training replays are
in-sample checks of closed-loop behavior, not an additional held-out set.

## Fit diagnostics

Imitation fit took 14.11 seconds. Training-label accuracy was 96.60%, but the
85.57% wait-label share makes this aggregate misleading: wait accuracy was
1,008/1,008; directional accuracy was **130/170 (76.47%)**. Matching individual
teacher states is not equivalent to recovering after the learner's own mistakes.

RL fine-tuning took 142.83 seconds for 6,144 actions, including optimization.
Training produced 41 recoveries, 31 deaths and five budget truncations, plus six
administrative closes at the training cutoff. These sampled training totals are
not a matched evaluation against the previous run. Light diagnostics/tests ran
alongside this experiment; its timing is not a controlled speed benchmark.

## Reproduce

Use the Python environment and local artifact prerequisites in `ACTION-RL.md`.
The output directory must not already exist.

```sh
.webtiles/bench/tactical/.rl-venv/bin/python .webtiles/bench/tactical/train_action_imitation.py --config .webtiles/bench/tactical/artifacts/action-pilot-v2/config.json --output /absolute/new/imitation-run
.webtiles/bench/tactical/.rl-venv/bin/python .webtiles/bench/tactical/audit_action_episodes.py /absolute/new/imitation-run
.webtiles/bench/tactical/.rl-venv/bin/python -m unittest discover -s .webtiles/bench/tactical -p 'test_*.py'
```

The run retains source snapshots, config/source/model hashes, demonstration arrays,
per-action raw observations, request logs, episode audits and evaluation summaries.
`test_action_imitation.py` checks that masked actions cannot be teacher labels and
that the masked likelihood's gradient trains only available actions.
