# Clear-only mild-discount screen

One fresh seed-0 run with +1 clear, all other rewards zero, gamma=0.9999 per
physical turn. All other configuration matches the clear-only gamma=1 screen:
24 enemies, 2048-turn deadline, semantic actions, exact D4 policy, maps, clumping,
initialization, PPO hyperparameters and validation placements.

Evaluate sampled and greedy at 500,224 decisions, then resume the full checkpoint
(optimizer, RNG and live worlds) to 1,000,448. Both stages retain their checkpoint
and results. Native macro reward discount and PPO duration-dependent bootstrap
use the same gamma, verified by the trainer. Raw episode reward remains equal to
the clear indicator, also asserted throughout validation.

Run branches/semantic-clear-only-v1/scripts/run_gamma9999.py with the GPU venv.
It builds separate gamma0.9999 libraries, keeps artifacts under ignored
learning-runs/semantic-clear-only-gamma9999, and writes both results into
results/semantic-clear-only-gamma9999.json. Each stage has a 2 GiB storage cap
and 10 GiB free-space reserve. Compare against gamma=1 at matching checkpoints.
One seed is a preliminary screen, not evidence of robustness.
