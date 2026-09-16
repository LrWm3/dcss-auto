# Tiny physical-turn cost from imitation

Seed-0 PPO from the preserved deterministic-controller imitation checkpoint.
Same settings as autoregressive-imitation-no-entropy, changing only reward:
+1 for clear, -0.00001 per physical game turn, zero kill/exploration/death rewards.
Gamma=1 and entropy coefficient=0. Fresh original PPO optimizer and zero critic;
no critic warm-up, KL limiter, imitation loss or new observation inputs.

The penalty is applied in floating point at every native primitive transition,
not rounded through integer milli-rewards. REST pays for every internal turn,
including the final turn on clear/death/timeout. Episode return is therefore
clear_indicator - 0.00001 * episode_physical_turns. Full evaluation asserts this
identity within 2e-5 float accumulation tolerance.

Keep 24 enemies, 2048 physical turns, training clumping/maps, validation placements,
and autoregressive policy unchanged. Evaluate both sampled and greedy at 0,
500,224 and 1,000,448 decisions on 1,024 held-out placements. Initial behavior must
exactly match the no-penalty run, excluding reward. Compare clears, timeouts,
physical turns, rest usage and navigation behavior. A small raw penalty need not
imply small optimizer effects because PPO standardizes advantages.

Isolated branch: branches/autoregressive-turn-cost-v1. Build scripts/assets.py;
run scripts/preflight.py; launch scripts/run_experiment.py with the GPU venv.
Preflight checks physical state/observations/masks unchanged versus no penalty,
macro reward difference equals the physical-turn cost (including REST), native
masks/transitions, D4, and PPO partial-rollout/checkpoint resume. Artifacts stay
in ignored learning-runs/autoregressive-turn-cost with 2 GiB cap/10 GiB free
reserve. Tracked summary: results/autoregressive-turn-cost.json.

## Completed results

Initial behavior matches the zero-penalty run exactly. Counts out of 1,024.

| Decisions | Mode | Clears | Deaths | Timeouts | Turns/episode | Rests/episode | Mean reward |
|---|---|---:|---:|---:|---:|---:|---:|
| 0 | sampled | 992 | 32 | 0 | 662.34 | 8.87 | 0.962127 |
| 0 | greedy | 967 | 32 | 25 | 695.40 | 8.72 | 0.937382 |
| 500,224 | sampled | 983 | 39 | 2 | 659.42 | 8.67 | 0.953367 |
| 500,224 | greedy | 793 | 37 | 194 | 910.24 | 8.09 | 0.765312 |
| 1,000,448 | sampled | 975 | 45 | 4 | 687.69 | 8.56 | 0.945272 |
| 1,000,448 | greedy | 351 | 25 | 648 | 1600.35 | 6.17 | 0.326770 |

Compared with zero penalty at 500K, sampled clears decrease from 998 to 983 while
mean episode turns decrease from 789.12 to 659.42. Greedy clears increase from
17 to 793. At 1M, sampled clears decrease from 980 to 975; mean episode turns
fall from 735.83 to 687.69; greedy clears increase from 78 to 351. Episode length
averages include deaths, so they are not conditional clear-completion times.

Loop replay reproduces greedy outcomes exactly. At 500K, all 194 timeout episodes
contain >=8 consecutive immediate movement reversals, versus 942 of 982 timeouts
without the penalty. At 1M, 640 of 648 timeouts contain such oscillations, versus
900 of 918 without the penalty. Stationary/blocked MOVE attempts: zero. Detailed
results: results/autoregressive-turn-cost-navigation.json. Generalized navigation
script accepts suite/result/output and stage/mode arguments for reproducibility.

Conclusion: this tiny penalty substantially reduces greedy failure relative to
zero penalty, especially at 500K, but does not preserve imitation navigation over
continued training. Sampled success remains high but is not improved; both final
modes remain below imitation's starting clear rates. One seed is a preliminary
comparison, not an established optimal coefficient or general causal explanation.
Training took 25.45 seconds, 1,161,813 physical turns; full training/evaluation
pipeline took 95.29 seconds, plus loop diagnostic replay. Preflight also verified
158 physical REST turns with the new penalty. All checkpoints preserved.

## Continuation to 10M

Authorized seed-0 continuation resumes the 1,000,448-decision checkpoint including
optimizer, model, simulator, RNG and training history. Original 1M artifacts remain
unchanged. No reward or PPO hyperparameter changes. Evaluation targets are 5M
and 10M; actual batch-aligned checkpoints are 5,000,192 and 10,000,384 decisions.
New validation summaries additionally report physical turns conditional on clear,
death and timeout, separating successful completion time from early deaths.

Launcher: scripts/continue_10m.py in the same branch. New suite:
learning-runs/autoregressive-turn-cost-10m. Results:
results/autoregressive-turn-cost-10m.json. Source checkpoint digest and original
training time recorded in continuation manifest. Same disk limits apply. Additional
training time is reported separately from cumulative time.

Continuation completed: at 5,000,192 decisions, sampled clears were 968/1024
(94.53%), deaths 38, timeouts 18. Successful clears averaged 924.86 physical
turns. Greedy clears were 73/1024, with 933 timeouts. At 10,000,384 decisions,
**both sampled and greedy clears were zero**. Sampled had 32 deaths and 992
timeouts; greedy had 21 deaths and 1003 timeouts. Thus the original tiny cost
only delayed deterioration. Cumulative training: 239.46 seconds, of which
214.01 seconds were additional training; continuation wall time 267.38 seconds.

## Coefficient sweep

Run `scripts/run_sweep.py` to compare n=0,1,3,10,30,100 with reward
`clear_indicator - 0.00001*n*physical_turns`. Reuse completed n=0 and n=1
checkpoints/results; train n=3,10,30,100 independently from the same original
imitation weights, with fresh zero critic/optimizer and identical seed-0 PPO
settings. Evaluate at 0, 500,224 and 1,000,448 decisions. No continuation from a
degraded policy, no entropy bonus, no other reward changes. Coefficients are
native floating-point compile definitions with separate libraries. Preflight
checks unchanged state/observations/masks and reward including internal REST
turns against the zero-cost environment. Evaluation checks the episode reward
identity to 1e-4 and identical initial behavior across coefficients.

Track sampled/greedy clears, deaths, timeouts, mean turns, successful-clear
turns, rest usage, and movement reversals. Historical n=0/1 files do not yet
contain conditional clear-turn metrics. Results are written incrementally to
results/autoregressive-turn-sweep.json; bounded checkpoints stay under
learning-runs/autoregressive-turn-sweep (2 GiB cap, 10 GiB free reserve).

The largest coefficient costs 0.6 reward over 600 turns and 2.048 over the full
deadline. It changes the objective enough that dying early may beat a late
clear; inspect deaths, not just speed or reward. A successful short-run
coefficient would still need longer training and additional seeds before claiming
it fixes the instability. No coefficient succeeding would rule out only this
reward range/settings, not prove a fundamental impossibility.

### Sweep training completed

All four new coefficients reached 1,000,448 decisions. Same seed and 1,024
validation placements; n=0 and n=1 reused as planned. At 1M:

| n | Cost/physical turn | Sampled clear % | Greedy clear % | Sampled clear-only turns | Sampled death % | Greedy timeout % |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 0 | 95.70 | 7.62 | 759.20 | 4.10 | 89.65 |
| 1 | 0.00001 | 95.21 | 34.28 | 707.77 | 4.39 | 63.28 |
| 3 | 0.00003 | 95.90 | 18.36 | 764.69 | 3.71 | 78.61 |
| 10 | 0.00010 | 95.90 | 25.88 | 723.83 | 3.22 | 71.19 |
| 30 | 0.00030 | 95.51 | 11.72 | 740.65 | 3.71 | 85.55 |
| 100 | 0.00100 | 95.80 | 30.96 | 707.09 | 3.81 | 67.09 |

Starting imitation: 96.875% sampled clears, 94.434% greedy clears. None of the
coefficients preserves greedy competence; there is no monotonic improvement
with penalty strength. Sampled clears remain near 95–96% at this horizon, with
no clear improvement over initialization. Some costs shorten successful sampled
clears versus zero cost, so the turn reward has effects, but increasing it 100x
does not solve the failure. Greedy failures are predominantly timeouts, not deaths.
This weakens the simple hypothesis that navigation deteriorates only because the
original penalty is too weak; it does not isolate an alternative cause or establish
long-run stability. One training seed is insufficient to rank close coefficients.

New runs took 24.90, 25.32, 25.35 and 25.35 seconds of training respectively;
combined build/preflight/training/validation wall time was 431.69 seconds (7.2 min).
Navigation replay is separately queued; completed n=0/1/3 replays reproduce the
original sampled and greedy outcomes. Their greedy timeouts containing >=8
consecutive movement reversals number 900/918, 640/648 and 776/805. Clear-only
times for historical n=0/1 above come from that replay. Remaining n=10/30/100
replays were still running when this summary was written.
