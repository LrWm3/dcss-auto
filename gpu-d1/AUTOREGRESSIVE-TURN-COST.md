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
