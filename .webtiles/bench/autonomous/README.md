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
  --cycles 10 --bootstrap-episodes 8 --actor-episodes 8 \
  --evaluation-episodes 5 --steps 200
```

The command is restartable: rerunning it against the same run directory
continues at the next completed cycle, reuses the current champion, and keeps
all replay, checkpoints, failures, and evaluations.

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
* `train_model.py`: behavioral cloning plus conservative counterfactual
  score-to-go updates.
* `counterfactual.py`: top-K plus random legal branches from exact checkpoints.
* `evaluate.py` and `train_crawl_agent.py`: parallel actors, replay, candidate
  evaluation, champion/challenger promotion, metrics, and restartable status.

## Persisted run layout

Runs contain the requested artifacts: `config.json`, `environment_version.txt`,
`champions/`, `candidates/`, `replay/`, `state_archive/`, `evaluations/`,
`rollouts/`, `metrics/`, `failures/`, and `latest_status.json`.

The live observation uses `score=-1` with `score_status=live` until Crawl ends.
Official final scores are read from morgues and seeded xlogs. Progression is
diagnostic only: incomplete paired games cannot cause a promotion. At least
five complete score pairs and a positive bootstrap lower confidence bound are
required. Truncated counterfactuals supply no fabricated score targets.

Menu-confirmation abilities such as Renounce Religion are intentionally not
enumerated in V1 because they are not one semantic action.  They are logged as
a bridge extension point rather than allowed to stall an actor.

The default engine is `crawl-tactical-sim`, the ordinary fast-play simulator
with the structured FIFO adapter. `crawl-tactical-chain-v2` remains available
for archived regression work. Earlier differences between short runs on these
binaries do not establish that either removes normal monsters; that would
require a paired engine comparison on identical seeds and actions.

## Disk safety and retention

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
