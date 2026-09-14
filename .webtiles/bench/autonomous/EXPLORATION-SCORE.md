# Scaled exploration objective v1

Enable with `DCSS_EXPLORATION_SCORE=1` before importing the environment/model.
This selects `crawl-general-explore-sim`; the historical `crawl-general-sim`
binary and old results are retained. Start fresh games: old engine checkpoints
are intentionally rejected by the normal engine-hash check.

```
raw_exploration = sum(100 * effective_depth * revealed_fraction)
exploration_credit = min(raw_exploration, 100 + 2 * native_score)
training_score = 10 * native_score + exploration_credit
```

60% of D:1 is 60 raw exploration points. D:10 has a full-floor budget of
1,000; Lair:1 1,000; Shoals:1 1,500; Zot:1 2,700. Dungeon effective depth is
its floor number; other branches use their configured base depth plus floor
number minus one, with a minimum of one. These are difficulty proxies, not
claims of equal actual danger.

The denominator is frozen at the first visibility update on the floor. It
includes initially non-solid in-bounds terrain and closed doors, not solid
rock. Water/lava and inaccessible pockets can therefore keep coverage below
100%. There is no completion cliff: every eligible tile contributes a fraction.
Tiles count on actual visibility, not just magic mapping. Digging cannot add
eligible tiles. Revisiting/forgetting cannot pay twice. Counting and summation
consume no RNG, and the policy encoder receives no hidden terrain mask.

The player save contains a bitmap and counters per branch/depth. For shifting
Abyss, repeated Pan/portals and repeated Ziggurats, v1 reuses the first layout's
coordinate mask/budget for that branch/depth for the entire game. That is a
bounded approximation, NOT a true percentage of all regenerated layouts.
Optional branches have their own budgets; reentering does not reset them.

The native morgue/highscore remains untouched. `score` and its official status
retain their original units for existing evaluation/promotion logic. Episode
reports and observations additionally contain:

- `native_score`, `scaled_native_score`
- `exploration_raw`, `exploration_credit`, `exploration_cap`
- `training_score`, `score_version`

Both live/cutoff and terminal reports use exact engine credit. Terminal credit
is written to the private actor's `exploration-final.json`, with version/seed/
native-score validation against the official death record. It is not inferred
from the previous observation. Missing data is an error, never zero-filled.
Generic evaluation summaries report mean native and mean training scores.

Replay keeps native `score_before/after` and adds `training_score_before/after`.
The learner uses combined-score returns/deltas in this mode and excludes shards
from other objective versions. Counterfactual targets use the same combined
score, with a distinct protocol name and rejection of mixed-unit continuations.
The persistent learner preserves policy weights but resets critic/optimizer
state when switching objectives. Model checkpoints record the objective version.
Promotion still uses native score: exploration cannot silently inflate claims
that native Crawl performance improved. No training run was launched here.

Build:

```
make -C crawl-0.35/crawl-ref/source GAME=crawl-general-explore-sim -j6 crawl-general-explore-sim
```

Validation: `smoke_exploration_score.py --output <new-directory>` using the
tactical Python environment. The smoke sets required mode flags, verifies live
credit, eight-step restored determinism, cutoff reporting and terminal reporting.
Evidence: `artifacts/exploration-score-smoke-01/results.json`.
In that death test native score was 19, scaled native 190, exploration credit
113.930292529231, and training score 303.930292529231.

## Broader collection protocol

The initial exploration training launch stopped without training because the
loop-only collector found no qualifying loops in 16 games. The v2 collector in
`try_visit_memory.py` no longer requires loops. It saves the initial state,
every 40th decision, the first safe enemy-free state at/after decision 20, and
any detected loop. It selects at most two states per seed: the ordinary
exploration state (initial-state fallback) and the latest checkpoint. If the
actor died, that latest checkpoint is labeled preceding-death with its exact
decision distance from death; it is not necessarily immediately before death.

All captured checkpoints remain available, but only the selected set receives
counterfactual compute. No evaluation states enter training. Run 02 repeats the
16 training seeds from the unsuccessful collection-only run; its 20 evaluation
seeds were never evaluated by that stopped run.

## Conservative refit after run 02 regression

Run 02's candidate collapsed to mean native score 0.05 on 20 seeds, versus
69.85 for its starting policy. Traces showed equipment cycling and movement
loops. Three noisy first-action continuations were being converted into equally
strong preferences, then optimized without a hard policy-drift limit.

`conservative_ranking.py` now filters preferences using paired rollout differences:
at least three valid, same-objective outcomes, a conservative one-sided 95% t
lower bound above both one score unit and a 1% relative margin. This is a
heuristic noise filter, not a multiple-comparison significance guarantee.
Fit uses eight epochs at 2e-5, a stronger reference KL penalty and all available
training anchors plus branch states. Each epoch is rolled back and fitting
stops if mean reference KL exceeds .02, any reference KL exceeds .15, or more
than 5% of reference greedy choices change. These are safety limits, not
evidence of improvement; optimizer state need not be restored because fitting
ends immediately after rollback.

Both the normal experiment and the reuse runner screen eight training-only
checkpoints with 256 decisions under each policy. The updated policy makes
every decision, with no old-policy fallback. Increased equipment cycling,
repeated movement without discovery, invalid results, or >10% aggregate score
regression reject the candidate before held-out evaluation. This checks the
first-action/continuation mismatch rather than assuming the labels remain
valid under a changed policy. It does not solve policy iteration in general.

Reuse without recollection:

```
DCSS_EXPLORATION_SCORE=1 .webtiles/bench/tactical/.rl-venv/bin/python \
  .webtiles/bench/autonomous/retry_exploration_fit.py \
  --source .webtiles/bench/autonomous/artifacts/v6-exploration-training-02 \
  --output .webtiles/bench/autonomous/artifacts/<new-retry-directory>
```

The retry uses five existing evaluation seeds only as a regression screen.
They are not fresh promotion evidence. There is no automatic promotion and
no evaluation-state training. Original artifacts/checkpoints remain untouched.
The run retains the existing 20 GiB disk pause / 22 GiB resume safeguards.
