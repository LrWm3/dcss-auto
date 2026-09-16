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
