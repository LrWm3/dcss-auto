# Demonstration-preserving tactical pilot

Run from the repository root:

```sh
/usr/bin/python3 .webtiles/bench/tactical/train_replay.py \
  .webtiles/bench/tactical/rl-replay-pilot-v1.json \
  .webtiles/bench/tactical/artifacts/rl-replay-pilot-v1
```

Output must not exist. The local verified checkpoint corpus and pinned lab
engine must be available. This does not deploy a model or change the game RC.

## What is being tested

A **linear DQfD-inspired baseline**, not a reproduction of deep DQfD:
permanent successful teacher demonstrations, bounded self-generated replay,
50/50 demo/self minibatches, target weights synced every 25 batches, double-Q
bootstrapping, equal-weight one-step and five-step targets, and continued
supervised margin updates. Pretraining fits TD and imitation together instead
of using classifier scores directly as Q values. Replay is uniform, not
prioritized; there is no neural network or L2 term. Updates are normalized and
clipped. Gamma is fixed to one for this finite-horizon task.

This follows the motivation of [DQfD](https://arxiv.org/html/1704.03732) and
[NetHack forgetting-mitigation experiments](https://arxiv.org/html/2402.02868v2),
without claiming their algorithms, scale, or results.

## Task and safety boundaries

The learner chooses tactical actions until death, floor change, proxy recovery,
stall, or the decision/turn budget. After proxy recovery the unchanged RC runs
for up to 600 decisions. Credit is attached to the final tactical transition:

- Death, including during RC continuation: -1.
- Floor change alive, or continuation ending observably recovered: +1.
- Unconfirmed recovery, stalls, or other unfinished budgets: 0.

This is a **bounded continuation objective**, not evidence that the encounter
was permanently solved or the floor cleared. Any floor change counts (including
ascent); future work should distinguish useful route progress from avoidance.
Budget endpoints terminate this finite task without bootstrapping. Continuation
actions belong to the fixed RC, not the learner. Long-term resource efficiency
and eventual full-game survival are not yet captured.

`credited-transitions.json` and `audited_credit` are authoritative for this
learner. The shared harness still writes historical `rewards.jsonl` and
`total_reward` with the old +/-100 proxy objective for compatibility; **those
values are not used by the replay trainer**.

An opt-in mask delegates poison, liquid fire, confusion, current clouds,
movement impairments, and unsafe unseen threats to the RC. It also prohibits
learner-controlled waiting beside a reachable opponent. This is not a safety
guarantee: the RC can fail, and waiting at range can still be dangerous.
Baseline, teacher, imitation, and Q comparisons all use the same shield.

## Comparison and provenance

The pilot uses five training cases and six validation cases from one separate
seed. Ten online training episodes; 59 total game trials. Compare RC, frozen
imitation, initialized Q, and final Q; report training separately from validation.
Only audited positive teacher episodes enter permanent demonstration replay.
No validation trajectories enter replay or imitation. The loader enforces seed
partitions, checkpoint integrity, and engine hashes. Reserved test is not run.
The old reserved seed was historically studied, so it is not a pristine final
test. One validation seed and one rollout per case cannot establish broad
generalization or robustness to combat randomness.

Each output includes resolved config/split provenance, source hashes, engine
hash, teacher data, credited trajectories, per-episode model snapshots, frozen
comparison results, and a completion summary. No automatic winner/deployment.
