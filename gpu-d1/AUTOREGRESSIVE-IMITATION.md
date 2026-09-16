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
