# Small kill reward from imitation

Test whether modest intermediate feedback preserves/improves competent imitation
under PPO. The only intended change versus autoregressive-turn-cost is +0.01 per
required kill. Reward: +1 clear + .01 * kills - .00001 * physical turns. Zero
exploration reward, zero explicit death reward. At 24 enemies the entire kill
budget is +.24, leaving clear reward dominant. Every internal REST turn still
pays the turn cost.

Use original streaming PPO, not the complete-episode collector: 512 worlds x 64
decisions, gamma=1, lambda=.95, entropy=0, same Adam/epochs/minibatches, zero critic,
and the original preserved imitation checkpoint. One seed (0), 24 enemies,
2048 physical turns, existing 256-map train distribution with one-third clumping,
LOS, sleep-status observation and autoregressive MOVE/ATTACK/WAIT/REST policy.
Separate native libraries change KILL_MILLI from 0 to 10. Existing libraries and
checkpoints remain intact. Direct control: results/autoregressive-turn-cost.json.

Evaluate at 0, 500,224 and 1,000,448 decisions on the same 1024 held-out placements,
sampled and greedy. Verify identical starting behavior and episode return identity
including kill count and physical turns. Compare clears, deaths/timeouts, successful
clear turns, rest usage and greedy movement-loop replay. Raw reward is not directly
comparable across objectives; clear rate and speed are primary behavioral measures.

Preflight rolls both native environments forward with identical actions from the
imitation policy for 512 steps across 16 worlds. State, observations, masks and
non-reward telemetry must match exactly. Per-step reward difference must equal
.01 times kills that step, including reset boundaries; exercise kills and REST.
Training and audit errors explicitly mark suite status failed.

Launcher: branches/autoregressive-turn-cost-v1/scripts/run_kill_reward.py.
Results: results/autoregressive-kill001.json and
results/autoregressive-kill001-navigation.json. Ignored checkpoints:
learning-runs/autoregressive-kill001, 2 GiB cap/10 GiB free reserve.
Training time and total wall time are recorded. One seed is exploratory evidence,
not an established coefficient ranking or proof of the cause of PPO degradation.
