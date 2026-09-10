# Autonomous Crawl policy training (V1)

This package is the replacement for the archived scenario-specific controller.
The old tactical system is preserved under
`.webtiles/bench/archive/TACTICAL-PRE-GENERAL.md` and the tag
`archive/tactical-pre-general-v1`.

## Launch

The repository wrapper is the shortest form:

```bash
./train_crawl_agent --run-dir .webtiles/bench/autonomous/runs/first --cycles 10
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

The live observation uses `score=-1` with `score_status=live` until Crawl ends;
death morgues are parsed for the official final score.  Short smoke evaluations
therefore use paired progression as a diagnostic metric.  Full-game promotion
runs should use terminal score as the primary metric once episodes reach an
end.

Menu-confirmation abilities such as Renounce Religion are intentionally not
enumerated in V1 because they are not one semantic action.  They are logged as
a bridge extension point rather than allowed to stall an actor.

The default engine is `crawl-tactical-sim`, the ordinary fast-play simulator
with the structured FIFO adapter.  `crawl-tactical-chain-v2` remains an
archived chained-encounter engine and should only be selected explicitly for
regression work.
