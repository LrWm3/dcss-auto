# Player-centered full-map policy

User-requested exploratory run: one fresh seed to 10M decisions, 24 ordinary enemies, a 2048 **physical game-turn** deadline, full terrain and enemy knowledge, sleeping enemies, and rest-to-full. No LOS or nearest-frontier guidance. Uses the existing 256 training layouts, 32 validation layouts (32 episodes each), and one-third clumped training placement. No ogres. Ordinary test layouts remain unused.

## Observation and architecture

The whole map is known from reset. All living enemies expose player-relative position, HP, type, and sleep status, including enemies behind walls or across the floor. Sleep is +1 asleep / -1 awake; empty slots are zero. No energy phase is exposed.

A 159×159 image is centered exactly on the player (index 79,79). It spans all possible relative displacements on the 80×70 world and supports rotations without cropping. Its three channels are terrain (floor +1, wall -1, outside-map padding 0), enemy HP /16, and enemy sleep status. The player is implicitly at the center. Absolute coordinates are used to construct the image but are zeroed before the learned network. Existing local/monster/scalar observations are retained, except the ring, frontier pointer, and route direction are zero. The full terrain is stored compactly in the rollout buffer and recentered inside the encoder.

The encoder uses three strided convolutions (3→8→16→16), followed by the existing two 128-unit hidden layers. Exact D4 averaging is retained. Both spatial channels and relative enemy records transform together. There is no pathfinder action or pathfinding suggestion.

## Rest and clocks

Rest is legal when HP is below maximum and **no awake enemy is within Chebyshev distance seven**, regardless of walls. Nearby sleeping enemies do not block rest. Rest executes normal primitive wait turns until full HP, an awake enemy enters/wakes within seven tiles, or the episode ends. Wake range remains six tiles, now distance-only: a sleeper within six can wake on the first rest turn and interrupt it. A sleeper exactly seven away permits recovery.

Every primitive turn counts against 2048, including turns inside rest. Rest is still one policy decision and one PPO discount step, with summed primitive rewards. Clock observation is physical turns /2048. Training duration is counted in policy decisions and physical turns are also reported.

Rewards: +1 kill, +3 clear, -4 death, -0.001 per physical turn. Exploration reward is zero because the whole map is visible from reset. Seen-floor progress consequently starts at the full floor count. This is an intentionally privileged task, not an information-matched comparison to the previous LOS policy.

## Training and checks

PPO batch 512, horizon 64, four epochs, logical minibatch 4096, learning rate .0003, gamma .99, lambda .95, entropy .01. Gradient accumulation uses chunks of 512 to bound convolution memory while retaining one optimizer step per logical minibatch. Evaluations run at 0/1/3/5/10M; sampled and greedy results are reported separately. The existing 2 GiB checkpoint budget and 10 GiB free-space minimum apply.

Preflight checks rest equivalence to repeated waits; full-HP and awake-range masks; sleep/wake interruption; interruption on the final physical turn; full-map status and zero frontier inputs; CPU/CUDA transition parity; extreme-offset recentering; spatial sleep/HP placement; padding; D4 equivariance; finite gradients; and a complete PPO update/resume. Native scenario tests use host code from the same simulator to avoid the CUDA compiler's oversized inlined test-kernel failure; a separate CPU/CUDA parity check exercises the production library.

```sh
gpu-d1/.venv/bin/python gpu-d1/branches/vision15-centered-map-v1/scripts/assets.py
gpu-d1/.venv/bin/python gpu-d1/branches/vision15-centered-map-v1/scripts/preflight.py
gpu-d1/.venv/bin/python gpu-d1/branches/vision15-centered-map-v1/scripts/pipeline.py
```

Run status/logs/checkpoints: `gpu-d1/learning-runs/vision15-centered-map/`. Preflight and completed summaries: `gpu-d1/results/centered-map-{preflight,training-summary}.json`. The previous LOS recovery-probe suite is not automatically applied because it assumes different visibility and rest rules.

## Launch and measured speed

All preflight checks passed. A full 32,768-decision PPO update took 43.05 training seconds (~761 decisions/s), projecting 3h39m training for 10M, excluding validation. Allow roughly four hours or more overall; later rollout cost and GPU load can change this. The first ordinary-floor checkpoint is at approximately 1M decisions.

## Performance update

Execution now uses a fused CUDA map builder and mixed-precision convolutions/linear layers with channels-last layout. The fused builder combines recentering, all eight D4 transforms, padding, and layout conversion, producing exactly the same map values as the original implementation. Model weights, optimizer state, PPO losses, probability normalization, and reported values remain float32; GradScaler protects FP16 backpropagation and is checkpointed. This preserves the task, information, architecture and logical minibatches, but does not guarantee bit-identical training trajectories.

On a 64-world batch, inference fell from 8.04ms to 2.38ms and forward/backward from 12.37ms to 5.05ms. Maximum probability discrepancy in the sampled checkpoint batch was 0.0000176, with identical greedy actions. A complete 32,768-decision PPO update fell from 43.05s to 8.66s (4.97× faster), projecting about 44 minutes of training plus evaluation. All 32 optimizer steps completed, all weights were finite and changed, and scaler/checkpoint resume worked.

The original run stopped safely at 65,536 training decisions. The accelerated run resumes its saved weights, optimizer, RNG, and environment state; no training progress was discarded. Its prior manifest is retained under `manifest-before-fused-amp.json`; the new manifest records execution version `fused_maps_amp_v1`. The initial 65,536 training decisions and initialization metrics used FP32. Allow roughly 60–75 minutes after relaunch, depending on validation and GPU load.

Evidence: `results/centered-map-performance.json`, `results/centered-map-profile.txt`, and `results/centered-map-fast-preflight.json`. Reproduce the accelerated PPO smoke test with `preflight.py --fast`. Optional standalone checks live under `diagnostics/centered-map-performance/`.
