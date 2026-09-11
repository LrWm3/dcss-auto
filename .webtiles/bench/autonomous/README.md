# Autonomous Crawl policy training (V1 in development)

See [FOUNDATION-RESULTS.md](FOUNDATION-RESULTS.md) for current evidence and
unmet acceptance criteria. Basic neural exploration/combat/descent is now
demonstrated; autonomous improvement on held-out score is still unproven.

See [UPDATE-INVESTIGATION.md](UPDATE-INVESTIGATION.md) for the investigation
after 22 cycles: cycle 3 lost an independent 30-pair audit, and update ablations
identify teacher-dominated training, nonpersistent learner weights, and narrow
counterfactual coverage as priorities for repair.

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

## Persistent learning and seed diversity (2026-09-11)

The learner now continues from its previous candidate regardless of promotion.
The champion is only the independently evaluated deployment baseline. Migration
initializes the learner from the current champion once; old rejected models are
preserved, not silently adopted. `learner/cycle-*.parent.json` freezes collection
and initialization; `*.ready.json` commits the candidate before evaluation.
Committed candidates are immutable on resume. Checkpoints carry separate Adam
states for imitation, critic, and preference learning.

Default collection is eight games/cycle: seven fresh training seeds plus the
previous lowest-scoring training seed (eight fresh if no usable predecessor).
`--actor-episodes` overrides the budget; existing partial-cycle seed plans remain
frozen. Actors use the continuing learner, not necessarily the champion.
Evaluation namespaces and promotion criteria are unchanged.

Fine-tuning uses at most 256 seed-balanced imitation rows and 2,048 critic rows
per cycle, instead of two full imitation passes. All retained, tagged
counterfactual comparisons feed policy preference updates, not just the latest
state. Comparisons from different continuation policies are never pooled into
one ranking. Replay remains bounded by the existing 20,000-row/2-GiB limits;
this is recent replay, not an unlimited lifetime dataset.

Archive collection continues beyond the first four state buckets, with up to
four snapshots/floor and 128/game. The most recent archived state gets an episode
outcome sidecar. Up to four states/cycle are branched, mixing recent/final and
rotating coverage. These are heuristic priorities, not a learned novelty system.
Only current-engine/current-bridge saves enter new branching. Monster order is
stable, restored legal actions are checked against the probe, and competing
actions share the continuation exploration RNG seed. This pairs exploration
randomness; it does not force different actions to consume identical game RNG.
Only fully completed scored continuations currently supply preference targets.

Research supports broad diversity, not eight as a proven Crawl threshold:
[Procgen](https://proceedings.mlr.press/v119/cobbe20a.html) demonstrates the
importance of diverse environments; [CoinRun](https://openai.com/index/quantifying-generalization-in-reinforcement-learning/)
reported overfitting even at 16,000 training levels. Levels are not equivalent
to whole Crawl seeds. Eight games/cycle is an initial throughput budget, with
seven new seeds each cycle rather than a permanent eight-seed training set.
Monitor held-out score and replay seed coverage before scaling further.

Validation: all 51 automated tests pass with live-engine tests enabled, including
snapshot restoration and low-space pause/resume. The persistent learner test
checks weight changes, all three optimizer histories across rejected candidates,
frozen parent plans, historical comparison replay, and seed-balanced sampling.
`artifacts/persistent-learner-smoke-v1` exercises real collection, branching,
learning, and evaluation with a process restart between cycles. Its small
20-decisions/floor budget is an operational test, not evidence of stronger play.

## Carried-over fast transport (2026-09-11)

The general adapter now carries over the proven tactical harness optimizations:
no Pexpect input delay; verified private copies of engine db/des caches; buffered
initial-plus-next observation logs; a bounded terminal tail. Actors writing full
training replay skip the duplicate environment event stream. Replay format is
unchanged; standalone environment logs advertise `initial_then_next_v1` in
`run.json` (the reset carries the first observation and transitions carry only
the next observation). Do not interpret these as the old duplicated event format.

Actor/screen concurrency is capped at six; independent counterfactual branches
also use up to six workers. Each branch has its own Crawl process, save directory,
and exploration RNG; results remain in deterministic task order. Confirmation
and audit worker counts remain those in their frozen protocol.

`engine_cache.py` adapts tactical/cached_env.py without its thread-unsafe global
spawn patch. The first successful cold launch publishes the template atomically
under a process lock. Subsequent launches verify checksums and make private byte
copies of db/des only, never character saves or RNG state. Default template root:
`artifacts/engine-cache`, overridable with `DCSS_GENERAL_CACHE_ROOT`. An engine
hash change selects a new template. Corruption fails closed; templates are not
silently trusted. The existing low-space guard still applies.

Small before/after validation, not a comprehensive throughput benchmark:

| Workload | Before / serial | After / parallel |
| --- | ---: | ---: |
| Two seeds, 80 fixed actions, two save/restores | 27.32 s | 7.21 s |
| Six 20-decision counterfactual continuations | 5.62 s | 2.59 s |

Every transport observation (including restored states) matched exactly. All
counterfactual records also matched, with no errors. The transport measurement
includes the first cold cache build; later startup/restores were 0.46–0.49 s.
These are approximately 3.8x end-to-end and 2.2x branch-batch improvements on tiny
workloads, not promised full-cycle speedups. Timing comparisons ran without
concurrent test loads; the branch run was repeated after the tests completed.

Evidence: `artifacts/transport-carryover-{baseline-v1,fast-v1}/results.json` and
`artifacts/transport-carryover-parallel-v2/results.json`. Reusable small checks:
`smoke_transport.py` (optional `--reference`) and `smoke_parallel.py`. All 52 tests
passed with live-engine tests enabled, including private cache isolation,
corruption detection, snapshot restoration, and low-space pause/resume.
`artifacts/transport-carryover-cycle-v1` also completed a short real training
cycle: two actor games, 48 actor decisions, 12 counterfactual action records,
candidate training and evaluation, zero recorded failures. No long run launched.
