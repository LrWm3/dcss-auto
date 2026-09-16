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

Preflight replayed 80 identical action batches in 16 worlds against gamma=1:
physics state, observations, masks and all outputs except discounted macro return
match exactly. Initial sampled clear rate also matches at 65.23%.

## Completed results

Counts out of 1,024 validation episodes.

| Decisions | Mode | Clears | Deaths | Timeouts | Rests/episode | Waits/episode | Turns/episode |
|---|---|---:|---:|---:|---:|---:|---:|
| 500k | sampled | 930 | 88 | 6 | 5.53 | 36.57 | 608.44 |
| 500k | greedy | 911 | 60 | 53 | 5.98 | 114.48 | 691.12 |
| 1m | sampled | 959 | 54 | 11 | 7.54 | 73.27 | 674.65 |
| 1m | greedy | 0 | 22 | 1002 | 0.47 | 1982.65 | 2004.58 |

At 500K, mild discounting improves greedy clears from the gamma=1 control's 11.8%
to 89.0%, with sampled clears essentially unchanged (90.8% versus 90.9%).
At 1M, greedy fails again: 0 clears, 97.85% timeouts and 1,982.65 waits/episode.
Sampled clears reach 93.65%, compared with gamma=1's 95.90%. Thus gamma=.9999
does not prevent the waiting collapse over this training interval. The early
greedy improvement is not sustained. One seed does not establish robustness or
the exact cause of the later regression.

Training took 55.73 seconds through 500K, then another 68.59 seconds through 1M
(124.32 seconds cumulative). Physical training turns: 1,139,269 at 500K and
2,437,962 at 1M. Full pipeline including native builds and validation: 279.13
seconds. No additional training was launched.
