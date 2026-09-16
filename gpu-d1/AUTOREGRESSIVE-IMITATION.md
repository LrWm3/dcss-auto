# Deterministic demonstrations followed by low-level PPO

Seed-0 pilot: generate 524,288 low-level decisions from the deterministic
observation-based controller on 256 training maps with one-third clumped spawns.
Keep MOVE/ATTACK directions distinct; retain WAIT and REST. Teacher priority:
weakest adjacent attack, safe rest, wait for visible awake enemy, approach visible
enemy, otherwise explore. Replan movement every turn (no exploration macro).
Evaluate this low-level teacher separately on the 1,024 held-out placements;
do not assume it exactly reproduces the previous semantic macro controller.

Behavioral cloning minimizes joint action negative log likelihood for eight
passes (minibatch 2,048, Adam .0003, gradient clip .5), with the existing exact-D4
128-wide autoregressive policy. Data include successful and unsuccessful episodes.
No validation trajectories are used as demonstrations. Bounded half-precision
observation buffers stay in GPU memory; there is no growing disk dataset.
Training agreement is diagnostic, not a held-out accuracy estimate. Teacher ties
need not be D4-equivariant, so not every label is uniquely representable.

Evaluate the cloned policy sampled and greedy before PPO. Then train for 1M new
policy decisions with +1 clear, zero other rewards, gamma=1 per physical turn,
entropy .01, and existing PPO settings. Evaluate at 500,224 and 1,000,448 decisions.
Reset Adam for PPO and initialize the untrained critic to zero; there is no
imitation loss or teacher intervention during PPO. Keep the same observations,
24 enemies, sleep/LOS and 2048-physical-turn terminal deadline throughout.
Report demonstrations, cloning time, PPO decisions/turns/time separately.

Teacher pathfinding uses remembered observed terrain, never hidden map geometry.
The student receives the existing local view, enemy records and frontier route
cue, not the entire remembered map. This information difference and imitation
rollout errors may limit performance. One seed and a short PPO budget do not
establish eventual performance or superiority over from-scratch training.

Branch: branches/autoregressive-imitation-v1. Run scripts/assets.py, then
scripts/preflight.py, then scripts/run_experiment.py using the GPU venv.
Tests cover native masks and physical transitions, rest interruptions, deadlines,
inactive worlds, D4 probabilities, entropy/log-prob gradients, partial final PPO
rollout and checkpoint resume. Evaluation asserts raw reward equals clear status.
Native/PPO gamma agreement is asserted. Artifacts stay under ignored
learning-runs/autoregressive-imitation with a 2 GiB cap and 10 GiB free reserve.
Tracked result: results/autoregressive-imitation.json.

## Completed pilot

All evaluations use 1,024 held-out placements. Teacher: 986 clears, 27 deaths,
11 timeouts (96.29% clears). Final cloning training action agreement: 99.71%;
this is training agreement, not held-out label accuracy.

| Stage | Mode | Clears | Deaths | Timeouts | Turns/episode |
|---|---|---:|---:|---:|---:|
| Imitation only | sampled | 992 | 32 | 0 | 662.34 |
| Imitation only | greedy | 967 | 32 | 25 | 695.40 |
| PPO 500,224 | sampled | 0 | 41 | 983 | 1975.44 |
| PPO 500,224 | greedy | 0 | 30 | 994 | 1988.62 |
| PPO 1,000,448 | sampled | 0 | 46 | 978 | 1969.28 |
| PPO 1,000,448 | greedy | 0 | 28 | 996 | 1992.62 |

The imitation checkpoint is a successful low-level initialization. Its six-clear
sampled advantage over the teacher does not establish superiority from one panel.
PPO did not improve it: both modes lost all clears. At 1M, sampled averages
1,528 movement actions, 363 waits, and 7.09 kills; greedy averages 1,866 movement
actions, 107 waits, and 1.71 kills. Thus this is primarily timeout with ineffective
movement, rather than the earlier semantic policy's almost-all-WAIT collapse.
The exact mechanism has not been diagnosed. Possible contributors include a
zero-initialized untrained critic, sparse delayed rewards, and entropy-induced
drift from a confident cloned policy. Do not treat these as established causes.

Demo generation: 5.84 seconds; eight cloning passes: 18.28 seconds; PPO training:
21.72 seconds. Pipeline including teacher and policy validation: 128.57 seconds.
The original imitation checkpoint remains at learning-runs/autoregressive-imitation/
imitation.pt; PPO snapshots include decision 0, 500,224 and 1,000,448. No further
training is launched as part of reporting these results.
