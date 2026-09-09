# Fresh-seed frozen evaluation

The unchanged selector recovered **27/30 encounters (90%)**, while fixed
`pursue:0` recovered **30/30**. The model has not demonstrated an advantage over
this simpler controller. This is new-seed evidence, unlike the earlier tuned
49/49 historical result, but it is still a small, difficulty-selected D1–D7
checkpoint sample from only five seeds, not full-game or D15 success.

## Protocol

Seeds 83029001–83029005 were reserved before controller evaluation, with six
replay-verified encounters per seed. The collection's mismatching encounter-019
remains excluded; the separately verified next-ranked same-seed encounter-034
is included. No tactical tuning or fitting occurred during collection/evaluation.

Controllers match revision de7e3f6. Model goal-selector-v1 remains SHA-256
`1f2b9cf7f525191cb4b2bf0c724bb95efdd43a26cf16db56befb9089d1efb7f0`.
Only the evaluator changed (1d8666e): explicit fresh-dataset loading, hash checks,
reserved-seed checks, and evaluation-only metadata. All 131 Python tests and
13 existing Lua checks passed. Production RC, engine and training split unchanged.

Each case ran the selector and six fixed goal/berserk combinations, with a
600-decision budget and the existing full-health, observable-safety plus
20 consecutive checked quiet-turn recovery endpoint. Berserk is permission,
not a guarantee of activation. Fixed pursuit is the bounded goal controller
with shared safety overrides, not unguarded repeated Tab.

## Results

| Policy | Recovered | Died | Unavailable |
| --- | ---: | ---: | ---: |
| Selector | 27 | 3 | 0 |
| Withdraw, no berserk | 24 | 3 | 3 |
| Withdraw, berserk permitted | 25 | 2 | 3 |
| Defend, no berserk | 28 | 2 | 0 |
| Defend, berserk permitted | 28 | 2 | 0 |
| Pursue, no berserk | 30 | 0 | 0 |
| Pursue, berserk permitted | 29 | 1 | 0 |

All rows cover 30 cases; unavailable options are neither victories nor deaths.
Combined: 210 trials, 191 recoveries, 13 deaths, six unavailable choices,
12,548 controller decisions. No stalls or budget truncations. All 30 selector
outcomes agree with their corresponding fixed-option replay. Every selector
failure has successful alternatives: three selection misses, no observed
controller coverage gaps.

All 191 recovered trajectories passed the independent full-health/quiet audit.

Selector per seed: 83029001=5/6, 83029002=6/6, 83029003=6/6,
83029004=5/6, 83029005=5/6. Thus the fresh worst-seed result is 5/6.

## Failure traces

1. **collection/encounter-001, seed 83029001, D:5 — withdraw without berserk.**
   Started at 56/56 HP against a clockroach and scorpion. Reached a previous
   resting location in four moves, then fought/waited there as orcs, an invisible
   wizard and an ogre arrived. Ogre contact reduced HP from 52 to 20; a late
   teleport did not resolve before the ogre killed the character. Withdraw and
   defend with berserk permitted, and pursue without berserk, recovered.
   A historical resting tile is not necessarily a safe destination now.
2. **collection/encounter-015, seed 83029005, D:2 — defend with berserk permitted.**
   Berserk activated at turn 1509. At 1516 the unsafe-hold check switched to
   stairs retreat. The character kept withdrawing through exhaustion/slow while
   gnolls followed, including a halberd wielder at reaching distance, and died
   at turn 1541. Defend without berserk and both pursuit variants recovered;
   pursuit with permission did not actually activate berserk in its winning run.
   The transition out of combat and continued retreat need reassessment.
3. **supplemental/encounter-034, seed 83029004, D:5 — withdraw with berserk permitted.**
   Kept routing to stairs under centaur fire, issuing 40 movement commands and
   four shared safety responses, no melee or berserk. Brief LOS breaks and healing
   did not establish safety; the centaur killed it at turn 3403. Both pursuit
   variants recovered, while all withdrawal/defend variants died. Retreat toward
   a destination can be worse than closing distance on a ranged attacker.

These observations suggest testing retreat viability, current destination safety,
and post-berserk commitment before relying on retraining alone. They do not prove
that always pursuing or never berserking is generally best. Keep this frozen
result as the baseline; if tuning on these failures, treat them as inspected
regression cases and reserve another seed cohort for subsequent generalization.

## Startup reconciliation and artifacts

Original `goals-fresh-v1` contains one zero-decision harness error in
collection/encounter-030 defend:1: the known Lair
`regret_index_lairdec_grave_grove` map-parser startup failure, not a death.
`goals-fresh-v1-retry` repeated that case's reset checks and all seven policies
unchanged; all recovered. Six already-completed duplicate outcomes/options/features
agreed. `goals-fresh-v1-combined` replaces only that startup-error row; originals
are intact and the combined manifest records their hashes and the replaced worker.

Reproduce with `evaluate_goals.py --fresh-evaluation --revised-controllers
--jobs 10 --output <new-directory>` using the existing pexpect environment.
No model was trained or deployed. Evidence is recorded in
[evidence/goals-fresh-v1.json](evidence/goals-fresh-v1.json).
