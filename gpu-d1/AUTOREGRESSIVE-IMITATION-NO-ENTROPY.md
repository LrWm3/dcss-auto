# PPO from imitation without entropy regularization

Fresh seed-0 PPO optimizer from the preserved deterministic-controller imitation
checkpoint. Only entropy coefficient changes, from .01 to zero. Sampling remains
enabled. No new demonstrations, critic pretraining, teacher overrides or imitation
loss. Keep clear-only reward (+1 clear, zero otherwise), gamma=1, 2048 physical
turn deadline, 24 enemies, clumped training distribution, and all other PPO settings.

Evaluate sampled and greedy on the original full 1,024-placement validation panel
at initialization, 500,224 and 1,000,448 new PPO decisions. Initial metrics must
match the original imitation experiment exactly. The original checkpoints and
failed entropy-regularized run are preserved for comparison. This tests whether
the stable handoff seen in the small diagnostic panel extends to full validation;
it does not assume that fine-tuning improves over imitation.

Launcher: branches/autoregressive-imitation-v1/scripts/run_no_entropy.py.
Artifacts: learning-runs/autoregressive-imitation-no-entropy (ignored, 2 GiB cap,
10 GiB free reserve). Result: results/autoregressive-imitation-no-entropy.json.
No native or trainer changes. Existing reward, gamma, mask and terminal checks
remain active; preserved checkpoint hash is verified before launching.

## Completed results

Initial sampled and greedy metrics match the preserved imitation run exactly.
Counts out of 1,024 validation episodes.

| PPO decisions | Mode | Clears | Deaths | Timeouts | Turns/episode | Rests/episode | Waits/episode |
|---|---|---:|---:|---:|---:|---:|---:|
| 0 | sampled | 992 | 32 | 0 | 662.34 | 8.87 | 57.25 |
| 0 | greedy | 967 | 32 | 25 | 695.40 | 8.72 | 56.21 |
| 500,224 | sampled | 998 | 25 | 1 | 789.12 | 8.88 | 56.94 |
| 500,224 | greedy | 17 | 25 | 982 | 1977.24 | 2.98 | 26.39 |
| 1,000,448 | sampled | 980 | 42 | 2 | 735.83 | 8.61 | 33.57 |
| 1,000,448 | greedy | 78 | 28 | 918 | 1936.05 | 4.19 | 16.07 |

The sampled policy avoids the previous catastrophic collapse. Its six-clear
improvement at 500K is small, and at 1M it is 12 clears below imitation alone.
No sustained improvement is established by this single seed/panel. Sampled
physical turns increase relative to imitation. Greedy behavior deteriorates to
17 clears at 500K and 78 at 1M, primarily through timeouts, despite relatively few
WAIT selections. Thus disabling entropy stabilizes sampled performance but does
not preserve greedy navigation; the precise greedy failure needs a separate audit.

Training: 12.47 seconds through 500K, 25.17 seconds cumulative through 1M;
1,136,486 total physical training turns. Full pipeline including validation:
94.93 seconds. Original imitation, intermediate and final checkpoints preserved.
No additional training launched.
