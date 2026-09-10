# Combat weighting and learner-state corrections — 2026-09-10

Run: `artifacts/action-dagger-v1`. Same action interface, cases, engine, split and
192-request recovery budget as `ACTION-IMITATION.md`. Test untouched; no production
deployment and no PPO fine-tuning in this experiment.

## Results

| Frozen policy | Training recovered / died / timed out | Validation recovered / died / timed out |
| --- | --- | --- |
| Previous unweighted imitation | 13 / 3 / 2 | 4 / 3 / 1 |
| Combat weighting only | 14 / 4 / 0 | 4 / 4 / 0 |
| Weighting + three correction rounds | 15 / 2 / 1 | 6 / 2 / 0 |
| Scripted pursuit teacher | 15 / 2 / 1 | 8 / 0 / 0 |

Previous imitation and teacher results are from the identical-case earlier run;
the two new models were replayed here. The correction-trained policy matches the
teacher's aggregate training outcomes and improves validation recovery count, but
does not beat pursuit. This is promising development evidence, not statistical
proof of generalization from one small validation seed.

Both ribbon-worm variants now recover. Their adjacent-enemy waits fell from
37/51 in the original imitation model to 0/3. Both water-moccasin variants still
die, with 22/13 adjacent-enemy waits in the final model. Some successful variants
also contain harmful waiting; the adder RNG-0 variant recovers only on request 192.
The failure is reduced, not eliminated. Neither model uses berserk in validation.

Combat weighting increased original-demo directional accuracy from 130/170 to
165/170, with all 1,008 other-wait labels still correct. Collection rounds:

| Round | Learner-state labels | Teacher disagreements | Recovered / died / timed out before that round's fit |
| --- | ---: | ---: | --- |
| 1 | 860 | 39 | 14 / 4 / 0 |
| 2 | 1,029 | 5 | 14 / 3 / 1 |
| 3 | 1,233 | 18 | 15 / 2 / 1 |

Total: **3,122 new labels, 62 disagreements**, added to the 1,178 initial examples.
Final aggregate in-sample label accuracy is 716/716 directions and 3,584/3,584 other
waits. These perfect training-label counts do not imply correct actions at unseen
states, as the water-moccasin failures demonstrate.

All 3,122 labels passed independent reconstruction of teacher decisions, executed
actions, masks, observation histories and disagreement counts. All 108 episode
records passed the game-transition audit: 82 recoveries, 21 deaths, three budget
truncations and two administrative closes across collection/evaluation. Do not
interpret these pooled counts as one policy's win rate. 202 Python tests and 13
embedded Lua checks passed. The cleanup interruption below was the only observed
harness issue; resumed evaluations completed. Nothing deployed.

Next useful experiment: broader **training-only** learner-state coverage, with
combat-specific rollout metrics (especially waiting beside an attackable enemy).
Do not move the failed validation encounters into training or claim that matching
a pursuit teacher can teach better tactics than that teacher supplies.

## Fixed protocol

Initialize from the previous **imitation-only** checkpoint, not its degraded PPO
checkpoint. Reuse the 1,178 audited training demonstration actions (18 variants
from six training seeds). Fit 20 more epochs with stratified sampling:

- Directional movement/bump attacks: target mass 60%.
- Wait with visible hostiles or an unseen-threat marker: 20%.
- Other waits: 20%.

Absent groups are renormalized. In the collected data the threatened-wait group
is empty, so the effective mixture is 75% directions and 25% other waits.
This keeps recovery waits but prevents them dominating the loss. It does not
categorically ban waiting in combat. The pursuit teacher still supplies all labels.

Save the combat-weighted checkpoint, then run **three predetermined rounds**:

1. The frozen learner controls all actions on all 18 training variants.
2. At every state, record the masked pursuit teacher's preferred action without
   executing it. Keep all trajectories, including deaths and budget exhaustion.
3. Add these learner-state labels to all previous labels and fit 10 epochs.
   Within each stratum, teacher/learner disagreements get twice the sampling weight.

Each epoch draws the current dataset size with replacement. Batch 128, Adam .0003,
gradient clipping .5; optimizer reset for each fit stage, fixed sampling seeds
42–45. The model architecture, feature hashing/history, action masks and teacher
are unchanged. The teacher uses no berserk, so this remains pursuit imitation,
not a learned superior tactical oracle.

After all fits finish, evaluate the combat-weighted checkpoint and the third-round
checkpoint deterministically on 18 training and eight validation variants each.
No intermediate validation or checkpoint selection. Validation remains only four
families on one previously studied seed; these are not eight independent cases.
This comparison combines added labels and extra optimization, so it does not isolate
the causal benefit of corrections versus an equal-compute weighting-only control.

## Label integrity

`train_action_dagger.py` records actual learner actions separately from teacher
labels and logs raw game transitions. `audit_dagger_labels.py` independently
recomputes teacher actions and strata from recorded states, checks executed actions,
masks and disagreement counts, and reconstructs every four-frame model observation.
Only training records are accepted; label array hashes are checked. The existing
episode auditor also verifies transitions, rewards, action availability and outcomes.

## Evaluation interruption and resumption

All three training rounds completed, but the first frozen evaluation encountered
a PTY close error (`Could not terminate the child`). No associated Crawl process
remained when inspected. The close implementation's short post-signal status poll
can race process exit under load; the new action adapter now waits up to three
seconds and retries closing **only after confirming its owned child has exited**.
A still-live child or unrelated error continues to raise. Regression tests cover
both the confirmed-exit retry and bounded failure for a live child.

No model was retrained. `evaluate_action_dagger.py` resumed the saved-checkpoint
comparison, reusing 16 audited complete trials and replaying only the two trials
recorded as administrative closes. Original evidence and an interruption note
remain. A separate evaluation manifest records the checkpoint hashes and changed
adapter/resumer hashes. The two administrative closes are not gameplay outcomes.

To resume an interrupted frozen evaluation:

```sh
.webtiles/bench/tactical/.rl-venv/bin/python .webtiles/bench/tactical/evaluate_action_dagger.py /absolute/existing/dagger-run
```

## Reproduce

Requires the local Python environment and parent artifacts from `ACTION-IMITATION.md`.
Use a new output directory.

```sh
.webtiles/bench/tactical/.rl-venv/bin/python .webtiles/bench/tactical/train_action_dagger.py --parent .webtiles/bench/tactical/artifacts/action-imitation-v1 --output /absolute/new/dagger-run
.webtiles/bench/tactical/.rl-venv/bin/python .webtiles/bench/tactical/audit_dagger_labels.py /absolute/new/dagger-run
.webtiles/bench/tactical/.rl-venv/bin/python .webtiles/bench/tactical/audit_action_episodes.py /absolute/new/dagger-run
.webtiles/bench/tactical/.rl-venv/bin/python -m unittest discover -s .webtiles/bench/tactical -p 'test_*.py'
```
