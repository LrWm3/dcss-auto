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

## Interpretation and follow-up diagnostics

The recurrent arm is a strong navigation result on this fixture distribution: 91.80% main known-stair and 94.53% exploration success, versus 27.73%/58.98% for the feed-forward control. The GRU reaches 77.34%/81.25% on longer routes and 32/32 on longer threat backtracking. Feed-forward fails all 32 longer threat cases by waking the enemy and dying; the GRU has no deaths in these main/long tests. Remaining GRU failures are timeouts. Immediate reversals fall from 145/88 per main known-stair/exploration episode to 5.75/2.90. Training took 3.59 minutes for feed-forward and 9.07 minutes for GRU, excluding validation, with about 2.72M/2.63M valid supervised examples.

**The gain is not evidence that the coarse global map has been learned well.** Resetting the GRU before every action produces zero success in all three main task groups and large reversal counts. In contrast, zeroing only its encoded global map while retaining recurrent state yields 92.97% known stairs, 92.58% exploration and 96.88% threat backtracking, close to normal performance. These are post-training observation/state interventions, not retraining; they demonstrate dependence under the tested conditions and do not establish what alternative training could learn.

A more targeted check uses 24 pairs with identical local crops and player statistics, but different remembered stairs outside the crop. With fresh hidden state, the GRU chooses the teacher's correct initial direction in 56.25% of cases, solving both members of only **3/24 pairs**. Global erasure gives 50% and 0/24. Earlier compact models solved 24/24, though trained under a different replay/architecture protocol. Thus this policy shows little use of distant goal location on this diagnostic. Its main improvement is consistent with learned temporal control over local exploration/backtracking, rather than demonstrated global route selection. It has not solved the original representation problem in full.

A useful next test would train on paired distant-goal examples that require different actions despite identical local histories, then check whether the GRU can learn to use the global information while retaining its navigation performance. Another control would retrain the GRU without global input. Neither is included in this run.

The feed-forward and recurrent arms share inputs, CNN branches and replay protocol, but GRU has more parameters (229,476 vs 130,020), different initialization and policy-dependent replay. A single seed does not isolate every architectural or optimization effect. Comparison against older models also changes the sequence-training protocol. These remain supervised synthetic navigation demonstrations, not evidence of PPO improvement or full-size Crawl generalization.

[Global-map erasure and paired-goal diagnostics](../../results/remembered-grid-symbolic-interventions.json).

## Full-size compute measurement

On 80x70 synthetic inputs, FP32, batch 512 inference and 256 learning decisions per optimizer batch:

| Model | Inference batch ms | Optimizer batch ms | Four-pass network-only decisions/s |
|---|---:|---:|---:|
| Feed-forward | 6.61 | 6.42 | 8,832 |
| GRU | 5.77 | 21.42 | 2,890 |

The recurrent optimizer timing includes 16 no-gradient burn-in steps and 16 learning steps for 16 sequences. The estimate includes symbolic preprocessing each forward pass, action sampling, value evaluation, clipped PPO-shaped loss, gradients and Adam; synthetic advantages/returns are used purely to measure compute, not to train a useful PPO policy. It excludes the simulator, rollout buffer, GAE and full pipeline overhead. There were no competing GPU jobs. Both models use FP32; prior compact estimates used AMP and batch 1024, so do not interpret raw differences as a matched speed comparison. This is an unoptimized first recurrent implementation; it does not establish a speed advantage over earlier models.

[Raw benchmark](../../results/remembered-grid-symbolic-performance.json). Reproduce with `symbolic_benchmark.py` only after training jobs have finished. `symbolic_interventions.py` reproduces the post-training checks; `symbolic_report.py` renders the result tables below.

<!-- measured-results -->
## Results

| Model | Known stairs | Exploration | Long known stairs | Long exploration |
|---|---:|---:|---:|---:|
| ff | 27.73% | 58.98% | 10.94% | 38.28% |
| gru | 91.80% | 94.53% | 77.34% | 81.25% |

Greedy held-out exits: 256 episodes each main task, 128 each long task.

| Model | Sampled known stairs | Sampled exploration | Main threat backtrack | Long threat backtrack |
|---|---:|---:|---:|---:|
| ff | 59.38% | 71.09% | 100.00% | 0.00% |
| gru | 82.42% | 92.58% | 100.00% | 100.00% |

| Model | Training seconds | Valid supervised examples | Collected decisions | Selected update |
|---|---:|---:|---:|---:|
| ff | 215.6 | 2,717,636 | 612,239 | 12,000 |
| gru | 544.1 | 2,634,245 | 450,574 | 12,000 |

Training time includes collection and optimization, excludes validation. Different valid-example counts result from terminal padding and policy-dependent trajectories; both arms receive 12,000 optimizer updates.

Resetting GRU state before every evaluation action gives known_stairs: 0.00%, exploration: 0.00%, threat_backtrack: 0.00%. This post-training intervention measures reliance, not the performance of a retrained memoryless model.

[Raw summary and provenance](../../results/remembered-grid-symbolic-summary.json).
