# Floor-clear learning experiment v1

**Update:** all three runs have been extended to 10 million decisions; see [the continuation results](LEARNING-10M.md). The original 3m results below are preserved.

Three independent PPO runs learned to clear enemies in the compact simulator. On a fresh 2,048-episode evaluation, sampled policies cleared **90.9–92.3%**, versus **45.7%** for random legal actions and **91.5%** for shortest-path pursuit. This establishes learning in this proxy task; it does not establish superiority to pursuit, generalization to new maps, or transfer to native Crawl.

## Learning curve

Each checkpoint evaluates 1,024 episodes on the same monitoring suite, with fresh environment initialization and fixed evaluation RNG seeds. Values below are ranges across three independent training seeds, not confidence intervals. All checkpoints were specified before training; the final checkpoint was evaluated regardless of its ranking.

| Training decisions per run | PPO collection/update cycles | Sampled-policy clear rate | Cumulative training-loop time |
|---:|---:|---:|---:|
| 0 | 0 | 43.6–45.1% | — |
| 131,072 | 4 | 60.2–62.0% | 0.70–0.91 s |
| 327,680 | 10 | 69.3–72.1% | 1.72–1.94 s |
| 1,015,808 | 31 | 83.6–85.4% | 5.16–5.43 s |
| 3,014,656 | 92 | 90.3–91.2% | 14.91–15.49 s |

One cycle collects 512 worlds × 64 decisions = 32,768 transitions, then performs four PPO epochs with 4,096-transition minibatches (32 optimizer steps per cycle). Checkpoint thresholds are rounded up to the next completed cycle. Improvement was already present at the first measured checkpoint; its exact onset was not measured.

![Learning curves](results/learning-v1/learning-curve.svg)

The headline evaluates sampled actions, matching the stochastic policy trained by PPO. Argmax evaluation was also recorded: final monitoring clear rates were 87.6–91.4%. Some deterministic policies time out while their sampled versions escape those behavior loops. Do not substitute sampled results for guaranteed deterministic behavior.

## Separate final test

The frozen final policies were evaluated on 2,048 episodes using root seed **1,200,000**, separate from monitoring seed **900,000** and the training streams. These are new placements and combat randomness on the same fixed map. Every vector slot contributes exactly its first completed episode, including deadline failures; faster-finishing worlds are not overrepresented. The same initial scenario/RNG suite is used for every policy, though actions cause subsequent random draws and trajectories to diverge.

| Policy | Clear rate | 95% Wilson interval | Mean enemies killed / 8 |
|---|---:|---:|---:|
| Wait | 0.0% | 0.0–0.2% | 0.00 |
| Random legal action | 45.7% | 43.6–47.9% | 5.38 |
| Shortest-path pursuit | 91.5% | 90.2–92.6% | 7.74 |
| PPO seed 0, sampled | 90.9% | 89.5–92.0% | 7.69 |
| PPO seed 1, sampled | 91.1% | 89.8–92.2% | 7.68 |
| PPO seed 2, sampled | 92.3% | 91.0–93.4% | 7.74 |

Final argmax clear rates were 86.9%, 88.5%, and 91.0%. Confidence intervals describe episode sampling for a fixed policy; they do not capture uncertainty over training seeds. Only three training seeds were run. Pursuit was an evaluation control, never a demonstration source, reward teacher, or training label.

## Frozen task definition

- One unchanged native seed-1057 map, 836 reachable floor cells; inert stairs and items. Player and eight enemies start at distinct cells sampled uniformly from this connected floor. No curriculum or scripted placement progression.
- Nine actions: north, east, south, west, northeast, southeast, southwest, northwest, wait. Moving into an enemy attacks it. Moving into a wall consumes a wait, although the agent's mask excludes wall moves. Every action consumes 10 aut. Diagonal traversal follows the compact simulator's eight-neighbor geometry.
- Player: 18 HP and the original prototype's fractional AC/EV/shield/regeneration parameters. No XP, skill changes, inventory actions, or equipment changes.
- **New proxy player attack:** 80% hit chance; uniform integer damage 1–4; no monster armor/evasion roll. Enemy HP is fixed by species at 8, 10, 12, 16, 12, 10, cycling through rats, frilled lizards, goblins, hobgoblins, quokkas, and jackals. The last two enemies repeat rat/lizard. These HP and player-attack rules are chosen task parameters, not a native player-melee port.
- Incoming melee reuses `sim.h`. Pursuit reuses its energy scheduler, shortest-distance navigation and bounded occupancy repair, now selecting a distance field for the player's current position. Monsters are awake and permanently know the player's position. Dead enemies leave occupancy immediately and cannot act. Killing the last enemy ends the episode before further retaliation.
- Observation: 206 floats containing a 9×9 local floor patch and enemy-HP patch, all eight enemies' relative positions/HP/species/alive flags (even offscreen), player HP, remaining-time information via elapsed ticks, and player coordinates. No recurrent memory; enemy energy and regeneration accumulator are not exposed. Static topology outside the local patch is not directly encoded, but the map is fixed. This is an intentionally generous observation, not native Crawl perception.
- Reward: +1 per kill, +3 additional for clearing, −1 for death, −0.001 per decision. No damage reward, pursuit imitation, or navigation shaping.
- End on clearing all eight, death, or a **256-decision terminal deadline**. Deadline failure is part of this finite-horizon task, with time observable; value targets do not bootstrap through it. On termination, outputs retain the completed episode's outcome/HP/ticks, and the next observation is from a resident reset. RNG continues across training episode resets.

Before training, an easier six-enemy setting (HP 4/5/6/8/6/5 and player damage 1–8) was rejected because random actions already cleared 96.6%. Increasing to eight enemies, doubling enemy HP, and reducing player damage produced the frozen setting above: monitoring random 44.2%, pursuit 91.4%. No task or hyperparameter changes were made between the three final training runs. Calibration files remain in the local ignored `learning-runs/` directory.

## Compute and implementation

The CUDA simulator and policy share resident tensors through a small C ABI. Each transition is followed by a new batched policy decision; this does not reuse the wait benchmark's multi-wait kernels. Observations, actions, rewards and rollout buffers remain on GPU, with custom kernels on PyTorch's current CUDA stream. The CPU reference calls the identical task rules.

PPO uses a 44,298-parameter MLP with two 128-unit tanh layers, separate action/value heads, Adam learning rate 0.0003, gamma 0.99, GAE lambda 0.95, ratio clip 0.2, entropy coefficient 0.01, value loss coefficient 0.5 applied to half-MSE, and gradient-norm cap 0.5. No search, demonstrations, pretrained weights, or explicit skills.

Hardware: i7-10750H and Quadro RTX 5000 Max-Q 16 GiB. PyTorch 2.6.0+cu124; custom kernels compiled with CUDA 12.0 and GCC 12. Full dependency versions are archived in [requirements-lock.txt](results/learning-v1/requirements-lock.txt).

At the final checkpoint, measured training-loop throughput was **194,560–202,158 decisions/s**. Per run, collection/inference/GAE took 7.81–7.98 seconds and optimization took 7.10–7.52 seconds. Timers synchronize CUDA at the boundaries. The three runs used 9,043,968 training transitions total. Timing excludes fixture/all-pairs-distance construction, CUDA initialization, evaluation, checkpoint serialization, and final reporting. It is not the duration of the whole experiment job. These are three run measurements, not a dedicated throughput benchmark under controlled clock/power conditions.

This is substantially below simulation-only wait throughput, as expected, but already makes a multi-million-decision learning experiment inexpensive. It estimates compute for this fixed, dense-reward combat task only. Sparse goals, new maps, fog of war, richer mechanics and long-term resource decisions can change both sample requirements and throughput. Matching pursuit here does not establish sophisticated tactical planning.

## Validation

[Learning tests](results/learning-v1-tests.log) passed:

- Exact full-state/RNG, observation, mask and outcome CPU/CUDA agreement across 1, 6 and 8 enemies, 37 worlds per case, 300 mixed random/pursuit actions (33,300 paired transitions), including repeated deaths, clears and resets.
- Occupancy bijections, valid living positions, removal of dead actors, HP and regeneration bounds, killed counts and deadline bounds checked along trajectories.
- Explicit free movement, last-kill/no-retaliation, terminal timeout, death and resident-reset checks.
- Non-default CUDA-stream producer/consumer test.
- Original wait-prototype self-test passed unchanged (both layouts and schedulers, 0/1/8/32/64 monsters).

These validate the proxy implementation, not native equivalence of the newly introduced mechanics. Device sanitizer limitations from [RESULTS.md](RESULTS.md) still apply; no new device sanitization claim is made.

## Reproduce

From the repository root, using a Python 3.12 environment with CUDA-enabled PyTorch:

```sh
python3.12 -m venv gpu-d1/.venv
gpu-d1/.venv/bin/python -m pip install -r gpu-d1/requirements-learning.txt
make -C gpu-d1 build/learn.so
gpu-d1/.venv/bin/python gpu-d1/scripts/test_learning.py

gpu-d1/.venv/bin/python gpu-d1/scripts/train_clear.py \
  --enemies 8 --steps 3000000 --seeds 0,1,2 \
  --output gpu-d1/learning-runs/clear-reproduction

gpu-d1/.venv/bin/python gpu-d1/scripts/report_learning.py \
  gpu-d1/learning-runs/clear-reproduction \
  --output gpu-d1/results/learning-reproduction
```

Output directories must be new, so reruns cannot silently overwrite results. Defaults are 512 training worlds, 64-step rollouts, and 1,024 monitoring episodes. The report's fresh suite defaults to 2,048 episodes and seed 1,200,000. For baseline-only runs use `--mode baselines --enemies 8` with another output directory.

Final checkpoints remain locally under `learning-runs/clear-v1/seed-{0,1,2}/policy-3014656.pt`, together with all intermediate checkpoints. Compact curves, configuration/source fingerprints, fresh-test outcomes and plots are tracked under [results/learning-v1/](results/learning-v1/). The raw source fingerprints captured at training time allow separating future rule or implementation changes from this result.
