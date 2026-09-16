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

## Completed results

Both runs completed at 500,224 decisions. All initial sampled/greedy metrics
match exactly between conditions. Counts below are out of 1,024 episodes.

| Gamma | Evaluation | Clears | Deaths | Timeouts | Rest uses/episode | Waits/episode | Raw reward | Game turns/episode |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 0.99 | sampled | 893 | 124 | 7 | 0.3506 | 9.24 | 25.342 | 508.59 |
| 0.99 | greedy | 922 | 95 | 7 | 0.0000 | 2.57 | 26.033 | 504.91 |
| 1.0 | sampled | 930 | 86 | 8 | 3.7119 | 37.75 | 26.123 | 590.13 |
| 1.0 | greedy | 921 | 95 | 8 | 0.0049 | 5.56 | 26.022 | 507.08 |

| Gamma | Training physical turns | Training seconds (excludes validation) |
|---|---:|---:|
| 0.99 | 1,188,362 | 64.57 |
| 1.0 | 1,207,029 | 60.65 |

Sampled gamma=1 improves clear count by 37 and reduces deaths by 38; raw reward
increases from 25.34 to 26.12. It uses REST 3.71 versus 0.35 times per episode and
WAIT 37.75 versus 9.24. Greedy clears are essentially unchanged (921 versus 922),
and greedy REST remains rare (five selections across the entire panel versus zero).

This is an early change in the action distribution, not reliable greedy recovery.
The untrained sampled policy rested 5.05 times per episode, so it is more accurate
to say gamma=1 suppresses resting less than .99 at this point, rather than claim it
has learned to rest more than initialization. The rest/wait distribution shifts
and sampled improvement are consistent with the objective hypothesis, but one
short run per condition does not establish robustness or eventual performance.
Physical training exposure differs by only about 1.6% in this matched screen.
No runs beyond the requested short budget were launched.
