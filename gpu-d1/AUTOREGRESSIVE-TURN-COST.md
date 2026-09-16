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
