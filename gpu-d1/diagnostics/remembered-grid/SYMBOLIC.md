# Two-scale symbolic map with optional recurrence

This is an adaptation of the proposed symbolic navigation representation to the existing simulator and synthetic demonstration screen. The local crop stays **15x15**, as requested. Two new seed-0 arms compare a feed-forward core (`ff`) with a 128-unit GRU (`gru`) under the same sequence-based training protocol.

## Inputs

Local navigation: four exclusive one-hot categories, unknown / known wall / known unvisited floor / visited floor. A fifth sparse channel indicates remembered down stairs. The crop is player-centered. Outside the finite map array is encoded as impassable boundary. The player is always at the crop center. This is exact remembered terrain, not just current LOS.

Global navigation: a fixed 16x16 grid covering the entire level extent, including unknown regions. Tile (x,y) belongs to bin (floor(16*x/W), floor(16*y/H)); bins are disjoint even on 80x70 maps. Each bin stores the four category fractions, normalized by its actual number of tiles, plus remembered-stair presence and a player-bin marker. Stairs use presence rather than a diluted fraction so a single known stair remains visible. The player marker locates the agent on this world-aligned map; absolute x/y are used only for constructing observations, not passed as scalar inputs to the network.

Tactical input is a separate 15x15 encoder receiving current visibility and the five existing enemy channels masked by visibility. Enemy information is not mixed into global terrain. HP and elapsed time are retained. Current fixtures have at most one enemy; multi-enemy ordinary-floor adaptation remains future work.

There are no frontier counts, frontier directions, distances, path-search outputs, or recommended destinations. The deterministic teacher may use routes to generate supervised targets, but those labels do not enter observations or evaluation actions.

## Architecture and training

Small local/global/tactical CNNs produce 64/96/32-dimensional embeddings, concatenated with two player scalars. The 194 inputs feed either a linear/ReLU 128-unit core or a GRUCell with hidden width 128, then the existing 19 masked individual-action logits. A value head is present for future RL but is not trained by this supervised screen.

The old shuffled-state replay cannot train temporal memory correctly. Both new arms instead use two bounded replay buffers (expert and learner-state), each retaining 1,024 sequences of 32 consecutive observations. Every 16 steps a new sequence is stored, with the preceding 16 steps as history. Initial histories and terminal tails are padded and marked invalid; sequences never cross episode boundaries. The GRU reconstructs its hidden state from 16 burn-in steps without gradients, then trains through 16 steps with gradients. Missing initial history leaves hidden state zero. This is truncated sequence replay, not exact reconstruction of arbitrary-length episode memory. Evaluation carries hidden state for the entire episode and resets on every batch reset. A post-training memory-reset evaluation checks reliance on recurrence.

Each update draws eight sequences from each buffer. Both arms learn from the same positions within sequences (at most 256 valid decisions/update); actual valid-example counts are reported. D4 augmentation transforms the entire sequence and directional labels consistently. The GRU does not consume the teacher label or a privileged past action. Both arms use Adam at 0.0003, gradient clipping 1, 12,000 updates, seed 0 and the existing expert/learner mixture schedule. Each arm collects its own learner trajectories, so their training data are not identical. The feed-forward control isolates recurrence within this new protocol; comparisons against older models also change replay/protocol and architecture.

Rollout collection uses 64 worlds, up to 128 steps per reset, and the existing 256 physical-turn deadline. Stored raw grids occupy about 704 MiB across both buffers, with additional masks/stats/labels. No replay buffers are written to disk; only best/latest checkpoints are retained. Checkpoints are selected by mean validation success across known stairs, exploration and threat-backtrack groups. The same held-out main/long and sampled tests are used. These are supervised/DAgger navigation tests on 32x32 synthetic layouts, not PPO training or full-size Crawl quality tests.

## Verification and commands

`check_symbolic.py` independently checks category partitioning, disjoint pooling on 32x32 and 80x70 inputs, fractions, stairs, player location and exclusion of enemy/visibility information from the global summary. It checks replay order, valid padding, recurrent resets, hidden-state influence and gradient flow, then runs short optimizer smoke tests for both arms.

```sh
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/check_symbolic.py
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/symbolic_suite.py
```

The suite trains and evaluates feed-forward then GRU, sequentially. Logs: ignored `learning-runs/remembered-grid/symbolic-{ff,gru}.log`. Reports: `results/remembered-grid-symbolic-{ff,gru}.json`. Existing completed experiments remain unchanged.
