# Sleep + doubled exploration reward + seen history

This is the next controlled toy-Crawl ablation after the sleep-only and hidden
first-seen reward runs. It keeps the native D1 fixture, eight enemies, the
six-tile sleep rule, combat, 256-decision deadline, PPO settings, and three
training seeds unchanged. It makes two deliberate changes:

- each floor cell that enters the player's 9x9 view for the first time earns
  `+0.002` (the previous exploration run used `+0.001`);
- the observation appends an aligned 9x9 binary channel. A one means that the
  corresponding floor cell has already appeared in this episode's view. The
  initial view is marked seen but earns no bonus. Walls and out-of-bounds cells
  are zero.

The policy therefore receives 287 inputs: the original 206 plus 81 local
history values. It does not receive a global explored-map bitmap.

## Fresh 2048-episode evaluation

Each row averages seeds 0, 1, and 2 at the final 10,027,008-decision
checkpoint. The evaluation suite uses the same seed (`1200000`) for all rows.

| policy | sampled clear | sampled kills | greedy clear | greedy kills |
|---|---:|---:|---:|---:|
| sleep only | 1.46% | 4.35 | 0.47% | 3.79 |
| hidden first-seen +0.001 | 0.81% | 4.16 | 0.37% | 3.86 |
| seen channel +0.002 | 1.14% | 4.28 | 0.99% | 4.09 |

This combination improved the greedy clear rate relative to both earlier
exploration runs, and brought sampled performance closer to the sleep-only
control. It still did not change the main failure mode: almost all episodes
timed out after roughly four kills, with the player still at full health. The
clear count remains small (70/6144 sampled episodes and 61/6144 greedy), so
three seeds are not enough to establish a reliable effect.

The result is consistent with the local history helping the policy avoid some
of the ambiguity in the novelty reward, while doubling the reward makes that
signal large enough to matter. It still does not provide a route to the
remaining enemies, so this is evidence of a modest learning improvement in the
toy task rather than evidence that exploration is solved. Because both the
history channel and reward scale changed together, it is a combined ablation,
not a clean estimate of either factor alone.

The matched seed-0 trajectory diagnostic also shows a tradeoff: timeout
episodes visited 91.9 unique positions and waited on 16.9% of turns, versus
111.9 positions and 9.0% waits for the sleep-only control. The extra reward
therefore appears to change action allocation more than it produces a broad
map sweep.

## Artifacts

- training run: `learning-runs/sleep-explore-seen-v1-10m-corrected/`
- fresh evaluation: `results/sleep-explore-seen-v1-10m-corrected-fresh-test.json`
- sampled trajectory diagnostic: `results/sleep-explore-seen-v1-10m-corrected-trajectory-sampled.json`
- build target: `make -C gpu-d1 build/learn_sleep_explore_seen.so`

The CPU and CUDA implementations matched exactly for 37 worlds over 300
mixed actions, including observations, masks, rewards, and state.
