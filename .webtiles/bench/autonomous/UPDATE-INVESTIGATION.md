# Investigation after 22 cycles without promotion

Source run: `artifacts/foundation-general-training-v4`.
Investigation artifacts: `artifacts/update-investigation-v1`.

The independent cycle-3 audit is complete. Its fixed manifest contains 30
fresh paired seeds, the two frozen checkpoints, environment hashes, and budgets
of 2,000 decisions per floor / 100,000 total. All seeds are in the held-out
audit namespace and are prohibited from training. It records an audit finding,
not automatic promotion or a rewrite of the original inconclusive confirmation.
The current engine differs from the original confirmation; those historical
and new results must not be pooled as one homogeneous experiment.

## Independent audit result

All 60 scheduled games produced official scores, with zero recorded exceptions.
The cycle-3 candidate was **confirmed worse** under the predeclared paired
bootstrap rule. V0 remains champion.

| Metric | V0 | Cycle 3 |
| --- | ---: | ---: |
| Games | 30 | 30 |
| Mean score | 117.2 | 56.97 |
| Median score | 44.5 | 34.5 |
| Maximum score | 599 | 268 |
| Paired wins | 18 | 11 |

One pair tied. Candidate-minus-V0 mean difference was -60.23 points. The
one-sided 95% bootstrap upper bound was -18.2, below zero; the corresponding
lower bound was -109.17. These are two one-sided bounds, not a central 95%
interval. All 30 seeds were distinct from prior registered evaluation seeds.

V0 had six floor-budget cutoffs and one adapter-stall cutoff; cycle 3 had six
floor-budget cutoffs. Those results use official scores at cutoff, as required
by the existing scoring policy. The other 47 games ended in death. The stalled
V0 game scored 123 on D:4, versus cycle 3's 31 on D:2. A post-hoc sensitivity
check excluding that pair still finds cycle 3 worse: 29-pair mean difference
-59.14, upper one-sided 95% bound -15.58. This sensitivity check does not replace
the primary predeclared 30-pair result.

Machine-readable results: `artifacts/update-investigation-v1/summary.json`.
The frozen audit manifest, all per-game results, and final decision are in
`artifacts/update-investigation-v1/evaluations/audits/cycle-0003-independent-audit/`.

## What the existing evidence actually says

The five-seed screening average overstates how broad the apparent regression is.
V0 scores `[6, 1065, 177, 37, 26]`: one seed supplies 81.2% of its total score.
Cycle 20 beats it on four seeds, but still loses on mean score. Cycle 21 beats
it on three seeds and has median 70 versus V0's 37, but mean 74.8 versus 262.2.
Mean score remains the objective; these observations show that a fixed five-seed
screen is weak evidence about general performance, not that median should
replace the objective. Repeated failures on the same seeds are not independent
evidence from repeated fresh trials.

On a fixed random sample of 512 retained **training** states, cycle 3 agrees with
V0 on 96.48% of decisions; cycle 21 agrees on 96.68%. Most changes are movement
direction. These are same-state diagnostics, not held-out performance estimates.

## Where the policy's learning signal comes from

Each cycle reloads the champion. Because none has been promoted, each candidate
starts from V0. The replay buffer persists, but rejected candidate policy weights
and optimizer state do not accumulate across cycles.

The learner then does two epochs of teacher imitation on current replay.
Recent cycles make roughly 37,000–40,000 individual teacher-label updates.
Labels come from the original scripted teacher, not observed better returns.
The score critic is a completely separate network, and action selection uses
only policy logits. Critic fitting cannot itself change what the actor chooses.
That isolation fixes the earlier destructive shared-output bug, but leaves
ordinary-play score learning disconnected from policy improvement.

Outcome-based actor updates use only the current cycle's one counterfactual
state, with at most one best/worst preference and 20 updates. Older preferences
are retained as replay records but are not accumulated into the policy preference
training call. When a challenger is rejected, its learned preference is lost
unless a later batch happens to relearn it.

Across the whole history, counterfactuals evaluated 69 actions at 20 distinct
states: eight D:1 states and twelve D:2 states. Eight had no visible enemy.
Only 54 actions had complete return estimates. Action coverage was:

| Action | Evaluations |
| --- | ---: |
| MOVE | 51 |
| WAIT | 9 |
| USE_ABILITY | 2 |
| REMOVE | 2 |
| WEAR | 2 |
| TAKE_STAIRS_UP | 2 |
| PICKUP | 1 |

The collector stops adding archive snapshots after the first four distinct
`(floor, enemies-visible)` buckets in each game. This favors early floors and
can exhaust the snapshot allowance before the character reaches its hardest
encounters. Counterfactual selection then cycles through a lexically sorted
archive instead of prioritizing deaths, uncertainty, or new progression.

There were no evaluated melee, potion, or targeted wand choices. Each action
uses only two continuations. Continuation exploration RNG seeds also depend on
the candidate action, adding noise to comparisons. Nonterminal continuations
produce no preference return, even when another continuation dies early.

## Isolated update replay

Using all 18,025 currently retained training rows, including 18,001 teacher
labels, with the live pipeline's two-epoch settings:

| Stage | Agreement with V0 on 512 training states | Evidence |
| --- | ---: | --- |
| Teacher update | 96.875% | 15 MOVE→MOVE changes; one PICKUP→WAIT |
| Separate critic | 96.875% | Actor parameters bitwise unchanged |
| Latest-state preference | 96.875% | One pair, 20 updates |

The preference margin increased from 0.4791 to 0.9819: it reinforced an action
that was already preferred. Equal agreement percentages do not imply identical
choices across stages. The full policy/gameplay results are retained separately.

The teacher-only checkpoint completed the existing five screen seeds with
scores `[4, 138, 17, 50, 28]`, mean 47.4. Thus a screen regression appears before
outcome-based actor updates are applied. First action divergences from the
recorded V0 runs occur on D:1 at turns 3, 26, 125, 15, and 61. The encoded
model inputs match at those comparisons (two raw observations differ only
in enemy array order). This localizes the initial changes to policy decisions;
it does not establish which individual route choice caused a later death.

The complete update (same teacher checkpoint, independent critic, latest-state
counterfactual preference) scored `[5, 709, 38, 39, 93]`, mean 176.8. It beats
the teacher-only checkpoint on four of five seeds, but remains below V0's
screen mean. This is evidence that the small preference update can materially
change gameplay, not that it is ineffectual. The five-seed comparison is still
too narrow to establish general improvement, and most of the gain comes from
one seed. The critic's actor isolation was verified, so it cannot account for
the policy weight differences between the two intermediate checkpoints.

## Reproducibility control

An older V0-versus-identical-V0 audit differed on seed `16845396515615345340`
(145 versus 275). Two fresh controls both scored 275 on D:4 after 2,234
decisions, with identical action sequences. The old outcome discrepancy was
not reproduced, but observations are not fully deterministic: 35 raw
observations differed; sorting enemy arrays left 15 differences in the action
lists. At decision 134, the unused target coordinates attached to Berserk were
`(0,1)` in one run and `(-1,1)` in the other.

`ga_enemy_scan` iterates a Lua hash table with `pairs`, and `ga_target` breaks
equal-distance ties by first occurrence. A stable enemy order / explicit
coordinate tie-break is needed, along with removing irrelevant targets from
untargeted abilities. This is a concrete interface issue, but it did not change
actions in this control and is not proven to explain the older score difference.
Do not edit the bridge during the frozen audit: subsequent games would then
use a different environment than earlier games in the same batch.

## Next changes supported by this investigation

1. Stabilize observation/action enumeration now that the frozen audit is complete,
   and repeat determinism checks on states with equal-distance enemies.
2. Give the learner persistent candidate state while keeping champion promotion
   separate. Save optimizer state and sample old usable preferences as replay.
3. Allocate outcome comparisons to many varied, informative archived states.
   Use consistent continuation randomness across alternatives and enough
   continuations to estimate uncertainty. Keep unfinished returns explicitly
   censored or evaluate to a declared scored horizon; do not label survival as
   worse merely because its continuation takes longer.
4. Reduce repeated teacher imitation to a measured competence constraint.
   Track navigation/combat changes and drift, rather than assuming more teacher
   updates imply better game score.
5. Evaluate promising checkpoints on broader independent seeds. Diagnose the
   fixed screen's sensitivity to its one large V0 result before treating it as
   a reliable gate for every future challenger.

These are proposed learning changes, not changes applied to the active trainer.
No new tactical rules or promotion exceptions were introduced.

## Reproduce / resume

From the repository root, use the existing tactical virtualenv Python with
`.webtiles/bench/autonomous/investigate_updates.py`. Pass:

```
--source .webtiles/bench/autonomous/artifacts/foundation-general-training-v4
--output .webtiles/bench/autonomous/artifacts/update-investigation-v1
```

Modes: `audit` resumes missing games in the fixed audit; `diagnose` reproduces
offline diagnostics and update ablations; `ablation-screen` evaluates the two
intermediate checkpoints on existing screen seeds; `summarize` persists screen
statistics and the final audit results when available. All runs retain the
20-GiB low-disk pause.
