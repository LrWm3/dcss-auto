# Short discounting training comparison

Two from-scratch seed-0 runs: gamma=0.99 control and gamma=1.0 without reward
discounting. Target 500,000 policy decisions each; final rollout is shortened so
both stop at 500,224 (512 parallel environments). Original rollout horizon stays
64 except the final partial rollout. Both use the same model initialization,
training/map seeds and PPO hyperparameters, including GAE lambda=0.95.

Everything else matches semantic-actions-v1: five semantic actions, 24 enemies,
256 training maps with one-third clumped placement, 32 validation maps × 32
placements, 15×15 LOS, sleep status, seen-floor count, 2048 physical-turn terminal
budget, +1 kill, +3 clear, -4 death, -0.001/turn, +0.002/revealed floor tile.
No forced-rest or forced-wait intervention is used in training or evaluation.

Native macro reward discount and Python duration-dependent PPO discount both use
the selected gamma. The native library exports its gamma and the trainer asserts
agreement for training and evaluation libraries. Gamma=1 means macro training
rewards equal raw sums, and subsequent-state bootstrapping has no time discount.
GAE lambda, entropy regularization, value learning and the explicit turn penalty
remain unchanged; this does not guarantee immediate learning of recovery.

Preflight compares old .99, new .99 and gamma=1 simulators on identical actions:
state/observation/mask equality, identical .99 outputs, gamma=1 raw reward equality,
and all other outputs unchanged. It also runs a small gamma=1 PPO job with a short
final rollout and verifies completed-checkpoint resume.

The sequential runner is `branches/semantic-discount-v1/scripts/run_experiment.py`;
run using `gpu-d1/.venv/bin/python`. Build with that branch's `assets.py`; test with
`preflight.py`. Artifacts: ignored `learning-runs/semantic-discount-500k`, 2 GiB
budget and 10 GiB minimum free disk. Checkpoint at roughly 250K without evaluation;
full sampled/greedy validation at initialization and the final 500K checkpoint.
The runner asserts identical initial validation behavior between conditions.
Final compact results: `results/semantic-discount-500k.json`.

This is a short learning screen with one seed on reused validation maps. Compare
clear/death/timeout rates, raw reward, rest/wait usage, physical turns and training
time. Fixed-policy reward ranking evidence comes from SEMANTIC-DISCOUNT-SWEEP.md;
this experiment tests whether the objective change alters what PPO learns early.
