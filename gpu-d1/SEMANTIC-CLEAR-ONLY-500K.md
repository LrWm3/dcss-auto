# Clear-only reward screen

Fresh seed-0 run to 500,224 decisions (500K rounded to 512 environments).
Reward is +1 on clearing and zero otherwise: no kill, exploration, death, or
turn reward. Gamma=1 in both physical-turn macro aggregation and PPO bootstrap.
Episode reward therefore equals the clear indicator. PPO entropy coefficient
0.01, GAE lambda 0.95, and other optimizer settings remain unchanged.

Same five-action semantic interface, exact D4 architecture, 24 enemies, 2048
physical-turn deadline, 15x15 LOS, 256 training maps with one-third clumped
placement, and 32 validation maps with 32 placements each. No forced controllers.
Both sampled and greedy evaluations run before and after training. Compare with
the shaped gamma=1 500K run, rather than confounding reward changes with gamma.
Reward scale and sparsity both change; this tests the proposed objective as a
whole, not the independent effect of any one removed reward component.

Build isolated branch semantic-clear-only-v1 with scripts/assets.py; run
scripts/preflight.py then scripts/run_experiment.py using gpu-d1/.venv/bin/python.
The pipeline waits for semantic-discount-1m to finish. Artifacts stay in ignored
learning-runs/semantic-clear-only-500k, with a 2 GiB budget and 10 GiB free minimum.
Results are saved in results/semantic-clear-only-500k.json.

Preflight confirms identical state, observations, masks and nonreward outputs
against the shaped gamma=1 simulator, exercises 657 rest turns, verifies macro
reward equals the clear indicator, and tests short final rollout plus checkpoint
resume. Full validation also asserts episode reward equals its clear indicator.

One seed on reused validation maps is an early learning screen, not evidence of
robustness. Track physical turns and training seconds alongside decision count.

## Completed results

500,224 decisions, 1,118,784 physical training turns, 54.27 training seconds
(excludes validation). Counts below are out of 1,024 held-out episodes.

| Reward | Evaluation | Clears | Deaths | Timeouts | Rests/episode | Waits/episode | Turns/episode |
|---|---|---:|---:|---:|---:|---:|---:|
| Clear-only | sampled | 931 | 87 | 6 | 4.97 | 57.01 | 621.31 |
| Shaped, gamma=1, 500K | sampled | 930 | 86 | 8 | 3.71 | 37.75 | 590.13 |
| Clear-only | greedy | 121 | 30 | 873 | 1.46 | 1689.24 | 1865.32 |
| Shaped, gamma=1, 500K | greedy | 921 | 95 | 8 | .005 | 5.56 | 507.08 |

Initial sampled clear rate was 65.23%, matching prior initialization. Final
sampled clear rate reached 90.92%, essentially equal to the shaped control's
90.82%. Greedy performance is poor: excessive waiting accompanies 85.25%
timeouts. Removing dense rewards allows learning but has not yielded a reliable
greedy policy in this short run. The experiment changes reward scale as well as
reward components, while keeping entropy/value coefficients unchanged; therefore
it does not isolate sparsity from their effective relative strengths. Sampled
and greedy policy differences must remain visible in interpreting this result.
All evaluated raw episode rewards equal their binary clear outcomes exactly.

## Continuation to 1M

Run scripts/continue_1m.py to resume the 500K checkpoint, including optimizer,
RNG and simulator state, with no reward or learning changes. The original suite
is preserved. New artifacts go to learning-runs/semantic-clear-only-1m; target
1,000,448 total decisions. Results go to results/semantic-clear-only-1m.json.
Additional training time is recorded separately from cumulative training time.
