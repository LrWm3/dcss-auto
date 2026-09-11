# Autonomous Crawl policy training (V1 in development)

See [FOUNDATION-RESULTS.md](FOUNDATION-RESULTS.md) for current evidence and
unmet acceptance criteria. Basic neural exploration/combat/descent is now
demonstrated; autonomous improvement on held-out score is still unproven.

This package is the replacement for the archived scenario-specific controller.
The old tactical system is preserved under
`.webtiles/bench/archive/TACTICAL-PRE-GENERAL.md` and the tag
`archive/tactical-pre-general-v1`.

## Launch

The repository wrapper is the shortest form:

```bash
./train_crawl_agent --run-dir .webtiles/bench/autonomous/runs/first --cycles 10
```

For a walk-away run, use `--forever`; stopping and rerunning the same command
resumes from the last completed cycle:

```bash
./train_crawl_agent --run-dir .webtiles/bench/autonomous/runs/first --forever
```

Use the existing ML environment, which contains CPU PyTorch, NumPy, and
pexpect:

```bash
PYTHONPATH=.webtiles/bench/autonomous \
  .webtiles/bench/tactical/.rl-venv/bin/python \
  .webtiles/bench/autonomous/train_crawl_agent.py \
  --run-dir .webtiles/bench/autonomous/runs/first \
  --cycles 10 --bootstrap-episodes 8 \
  --evaluation-episodes 5 --decisions-per-floor 2000 --total-steps 100000
```

The command is restartable: rerunning it against the same run directory
continues at the next completed cycle, reuses the current champion, and keeps
all replay, checkpoints, failures, and evaluations.

Each training cycle now collects exactly three champion-policy games: two fresh
training seeds and the lowest-scoring training seed from the previous cycle.
Official budget-cutoff scores count; crashes and missing scores do not. Ties
are broken by numeric seed. The first cycle chooses its retry from bootstrap;
if the previous batch has no usable training score, all three seeds are fresh.
Screen/confirmation/audit seeds are never eligible for this curriculum.

`training_seeds/cycle-NNNN.json` freezes the selected seeds, source score, and
independent exploration RNG seeds before any actors start. Retries use new
exploration randomness each cycle, while restarting a partial cycle reuses its
exact plan. Fresh seeds occupy namespace A, disjoint from confirmation D and
audit E. The selection ledger is permanent even after heavy-data retention.
The historical `--actor-episodes` option is superseded by this three-game policy.

For a bounded unattended window, schedule one complete resumable cycle at a
time. An already-running job keeps the lock; the scheduler waits and resumes
after it exits:

```bash
.webtiles/bench/tactical/.rl-venv/bin/python .webtiles/bench/autonomous/schedule_training.py \
  --run-dir .webtiles/bench/autonomous/artifacts/foundation-general-training-v4 \
  --hours 8
```

`schedule.json` records the deadline and `metrics/scheduled-training.log`
records each launch and exit. A cycle already in progress can finish slightly
after the wall-clock deadline; the scheduler never terminates it mid-game.

## What is implemented

* `general_env.py`: reset/load, structured observation, variable semantic legal
  actions, one-action stepping, exact Crawl save/restore/clone boundaries.
* `general_bridge.lua`: player/map/monster/inventory/spell/ability/status state;
  movement, melee, wait, stairs, quaff, read, fire/throw, cast, abilities,
  wield/wear/remove, and pickup actions.
* `teacher.py`: existing pursuit-style behavior used only for bootstrap data.
* `features.py`, `model.py`, `policy.py`: action-conditioned scoring over the
  current legal-action list; no fixed command output layer.
* `collect.py`: actor trajectories and restorable initial states.
* `train_model.py`: anchored behavioral cloning, an independent score critic,
  and small paired-state counterfactual preference updates with replay KL.
* `counterfactual.py`: top-K plus random legal branches from exact checkpoints.
* `evaluate.py` and `train_crawl_agent.py`: parallel actors, replay, candidate
  evaluation, champion/challenger promotion, metrics, and restartable status.

## Persisted run layout

Runs contain the requested artifacts: `config.json`, `environment_version.txt`,
`champions/`, `candidates/`, `replay/`, `state_archive/`, `evaluations/`,
`rollouts/`, `metrics/`, `failures/`, and `latest_status.json`.

The fork exports read-only `you.game_score()`, using the same standard-game
formula as final scoring, without a victory bonus while the game is ongoing.
Observations expose `score_status=live_official`; `get_game_score()` works during
play. Unsupported old engines and custom Sprint scoring return unavailable,
never a fabricated score. Final scores still come from morgues and seeded xlogs.
At episode-budget cutoffs the collector records `score_status=cutoff_official`
and the current score, keeping `terminal=false` and `truncated=true`. Evaluation
and replay return targets accept these scores. Intermediate live scores are not
per-turn rewards; short counterfactual horizons remain separate from full-episode
budget cutoffs and do not automatically become final-return targets.

### Screen, confirmation, and audit

`selection.py` implements `screen-confirm-audit-v2-cutoff-score` for future batches:

* The existing five seeds are a cheap screen, never promotion evidence. Broken
  candidates, severe loop regressions, and non-improving mean scores fail the
  screen. Incomplete score pairs are inconclusive.
* A promising candidate and champion are frozen and run on 30 fresh paired
  seeds (60 games, four workers). Only after the entire batch finishes, a
  one-sided 95% paired percentile-bootstrap lower bound above zero promotes.
  The protocol fixes 10,000 resamples, bootstrap RNG 42, and zero margin;
  the historical `--promotion-margin` setting does not override this protocol.
* Inconclusive candidates remain available, but relabeling the same checkpoint
  pair reuses its original batch, rather than buying another chance on new
  seeds. Budget-truncated games with official scores count normally; missing
  scores and crashes remain inconclusive. Confirmed-worse candidates are not promoted.
* Every five completed cycles, a separate fresh 30-pair audit compares the
  current champion with the frozen original V0. Audits report results but
  never promote or change the policy.

Checkpoints, environment hashes, budgets, seeds, and protocol are persisted in
each batch's `manifest.json`. Per-game results survive restart; unfinished games
are resumed by rerunning only the missing trials on the same seeds. A run lock
prevents concurrent training/confirmation mutation. Restarting training during
a frozen confirmation resumes that batch before any further training.

Confirmation and audit use separate reserved seed namespaces. Their observations,
snapshots, and results are tagged as held-out; collection, replay loading, and
counterfactual entry points reject using them as training data.

`evaluations/selection_protocol.json` records the fixed rule;
`evaluations/confirmations/<label>/status.json` records live completion and the
final decision; `evaluations/audits/` records scheduled baseline comparisons.
The root status points to the active confirmation. To confirm an already
screened candidate (repeat exactly this command to resume):

```bash
.webtiles/bench/tactical/.rl-venv/bin/python .webtiles/bench/autonomous/selection.py \
  --run-dir .webtiles/bench/autonomous/artifacts/foundation-general-training-v4 \
  --candidate .webtiles/bench/autonomous/artifacts/foundation-general-training-v4/candidates/cycle-0003.pt \
  --label cycle-0003-confirmation-v1 --screen-cycle 3
```

The command above documents the historical V1 batch. Its frozen environment and
decision are not rewritten or rerun under V2. On the next training launch,
the run-level V1 protocol is archived before declaring V2 for future batches.
Existing manifests keep their original rule and hashes. The previous engine is
retained at `artifacts/engine-archive/crawl-tactical-sim-before-live-score`;
old snapshots still require their matching engine unless explicitly migrated.
New archive IDs include the engine hash, and counterfactual selection skips
old-engine saves rather than trying to restore incompatible snapshots.

The score API is in fork commit `c51f74b`. Rebuild the console simulator with:

```bash
make -C crawl-0.35/crawl-ref/source -j4 GAME=crawl-tactical-sim crawl-tactical-sim
```

`test_live_score.py` checks score acceptance, replay targets, protocol migration,
and (with `CRAWL_STORAGE_LIVE_TEST=1`) equality between a live cutoff score and
the official quit score from a copied checkpoint, with no turn advancement.

There are no interim significance decisions. The 95% bound is approximate and
per comparison, not a lifetime false-promotion guarantee across unlimited
challengers. Thirty pairs improve evidence over five but may remain inconclusive,
especially with skewed scores. The scheduled V0 audits provide an independent
view of cumulative progress; they do not eliminate repeated-testing concerns.

### Decision budgets and update isolation

`--steps` is now an alias for `--decisions-per-floor` (default 2,000), not a
whole-game cap. Counts accumulate separately for each branch/floor and survive
revisits within an episode. Descending to a new floor grants that floor its own
allowance; stair bouncing does not replenish earlier floors. The default global
safety cap is 100,000 decisions. Sixteen consecutive decisions without advancing
game time trigger a separate adapter-stall cutoff. Waiting counts as a decision.

Administrative cutoffs save a restorable checkpoint and report `truncated`,
`truncation_reason`, `decision_budget`, and `resume_checkpoint`. They are not
deaths; they receive the fork's actual current non-winning score. Resumption is explicit: these
checkpoints are loadable through `GeneralEnvironment`, not automatically retried
forever. Counterfactuals still have a separate, explicit continuation horizon.
Existing configs migrate `steps_per_episode` to `decisions_per_floor` on restart.
Use a new evaluation directory when comparing policies under the new protocol;
old whole-game-cutoff results are not comparable final-score pairs.

Model V2 has fully separate policy and return networks. Old V1 checkpoints load
with policy logits unchanged. Absolute-score regression only updates the critic;
it cannot silently replace policy logits. Actor updates are smaller anchored
teacher corrections and comparisons of completed counterfactual returns from
the same state. Incomplete comparisons do not provide preferences. This fixes
the demonstrated overwrite bug, not the broader problem of learning strong play.

Menu-confirmation abilities such as Renounce Religion are intentionally not
enumerated in V1 because they are not one semantic action.  They are logged as
a bridge extension point rather than allowed to stall an actor.

The default engine is `crawl-tactical-sim`, the ordinary fast-play simulator
with the structured FIFO adapter. `crawl-tactical-chain-v2` remains available
for archived regression work. Earlier differences between short runs on these
binaries do not establish that either removes normal monsters; that would
require a paired engine comparison on identical seeds and actions.

## Disk safety and retention

Heavy cycle artifacts have an **eight completed-cycle** retention window, plus
all active/incomplete work. With 9 completed cycles (IDs 0–8), cycle 0 expires.
Maintenance runs automatically during training and after cycle completion.
It removes old completed replay shards, compressed observation/terminal logs,
and generated `.dsc/.db/.idx/.lux` caches from attributable simulation folders,
including finished confirmations and scheduled audits. Completed bootstrap
actor logs/caches expire with cycle 0. Replay can expire sooner under its existing
byte/row cap.

It preserves scores, decisions, seed registries, manifests, models, morgues,
snapshots, metrics, and failure evidence. Files from unknown legacy workspaces
without reliable ownership/completion metadata are conservatively retained;
new counterfactual workspaces are cycle-scoped. This is not a total run-size cap.
No directory trees are deleted, and symlink targets are excluded. Every removed
file is logged in `metrics/heavy_retention.jsonl`; deleted logs/caches are not
recoverable except by rerunning the simulation (selected saves remain).

Preview cleanup, or apply it while no training process owns the run:

```bash
.webtiles/bench/tactical/.rl-venv/bin/python .webtiles/bench/autonomous/retention.py \
  --run-dir <run-directory>        # dry run; add --apply to delete
```

Training pauses before new game actions, launches, snapshots, compression writes,
and model saves when the run filesystem has less than **20 GiB free**. It polls
every five seconds and resumes at **22 GiB free**. Live Crawl processes remain
waiting for input; the pause itself does not advance the game. This is a boundary
check, not a filesystem reservation: other programs and in-flight writes can
still consume space. Use `./train_crawl_agent --run-dir PATH --status` to see the
live `paused_low_disk` phase and free-space readings. Per-worker pause records
are persisted in `storage_pauses/`; policy is persisted in `config.json`.

Completed replay is gzip-compressed and read transparently by the learner.
At collection/phase boundaries the oldest complete replay shards are evicted
until both the **2 GiB compressed / 20,000 transition** limits are met. Active
and incomplete shards are excluded, so these are completed-buffer limits, not
a hard cap on the whole run. Results and eviction records remain in the result
sidecars and `metrics/storage.jsonl`. Evicted trajectories cannot be recovered
from the retained summaries; checkpoints and snapshots are never pruned.

Successful episodes with durable replay discard duplicate `events.jsonl` logs
and gzip terminal logs. Successful evaluations/counterfactuals, which have no
separate replay, retain compressed event logs. Failures, interrupted episodes,
all saves, state archives, models, results and metrics are preserved. Those
protected artifacts can still grow indefinitely; the low-space pause is the
final safeguard, not automatic permission to delete them.

On restart, completed actor episodes are reused and incomplete replay is moved
to `failures/invalid_states/` before retrying. Unfinished games restart, rather
than continuing their exact last in-memory turn. Existing completed replay is
compressed automatically; only actor log paths explicitly recorded in its
result sidecar qualify for duplicate-log cleanup.

Validation (2026-09-10): 16 tests passed including an opt-in real-engine
pause/resume test with mocked disk readings. The test verifies no command is
sent while paused and exactly one decision executes after recovery. Run with:

```bash
CRAWL_STORAGE_LIVE_TEST=1 .webtiles/bench/tactical/.rl-venv/bin/python -m unittest discover -s .webtiles/bench/autonomous -p 'test_*.py'
```

`artifacts/storage-smoke-v1` completed two collect/train/counterfactual/evaluate
cycles with compressed replay and zero recorded failures. Tests also cover
whole-shard byte/row eviction, protected artifacts, score preservation through
compression, pause hysteresis, and exclusion of incomplete replay from learning.
