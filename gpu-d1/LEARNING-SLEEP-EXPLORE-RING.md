# Sleep + doubled exploration reward + 11x11 frontier ring

This run keeps the fixed native D1 map, eight enemies, six-tile sleep rule,
combat, 256-decision deadline, PPO settings, and three seeds unchanged. It
uses the corrected doubled first-seen reward (`+0.002` per newly revealed
floor cell in the 9x9 view) and adds a compact 40-value observation channel:
the outer ring of an 11x11 window centered on the player. A ring value is one
when the underlying cell is floor and has not yet entered the 9x9 reward view.
Walls and already-seen floor are zero.

The ring is a one-step frontier preview. The current 9x9 view shows the
terrain needed to choose a legal move; the ring tells the policy which move is
likely to expose new floor on the next observation. The resulting policy has
246 inputs (the original 206 plus 40 ring values).

## Fresh 2048-episode evaluation

Each row averages seeds 0, 1, and 2 at the final 10,027,008-decision
checkpoint. The evaluation suite uses the same seed (`1200000`) for every
policy.

| policy | sampled clear | sampled kills | greedy clear | greedy kills |
|---|---:|---:|---:|---:|
| sleep only | 1.46% | 4.35 | 0.47% | 3.79 |
| doubled reward + redundant 9x9 history | 1.14% | 4.28 | 0.99% | 4.09 |
| doubled reward + 11x11 frontier ring | **23.37%** | **6.55** | **18.34%** | **6.06** |

This is a large improvement at the same 10M-decision budget. Timeout rates fell
from roughly 98% to 75% sampled and 79% greedy. The matched seed-0 trajectory
diagnostic shows why: timeout episodes visited 172 unique positions and waited
on 2.2% of turns, compared with 112 positions and 9.0% waits for sleep-only.
The same diagnostic estimates about 551 newly revealed floor cells per timeout
episode, versus about 327 for the hidden-reward policy. The policy is now
moving through the map and engaging substantially more enemies instead of
settling into local combat/wait behavior.

The result is strong evidence that the prior exploration bottleneck was partly
representational. The 9x9 history channel was redundant because the simulator
marks every currently visible floor cell as seen before constructing the
observation. The outer ring supplies the missing action-conditioned frontier
signal. This still is not global search: the policy only sees a one-step local
preview, and the result is specific to this toy task and reward.

## Artifacts

- training run: `learning-runs/sleep-explore-ring-v1-10m/`
- fresh evaluation: `results/sleep-explore-ring-v1-10m-fresh-test.json`
- sampled trajectory diagnostic: `results/sleep-explore-ring-v1-10m-trajectory-sampled.json`
- build target: `make -C gpu-d1 build/learn_sleep_explore_ring.so`

The CPU and CUDA implementations matched exactly for 37 worlds over 300
mixed actions, including observations, masks, rewards, and state.

## 30M continuation

The same checkpoints were resumed to 30,015,488 decisions without changing
the task or optimizer. On the same 2,048-episode fresh suite, the three-seed
means rose to **41.39% sampled clear** and **37.32% greedy clear**, with 6.97
and 6.67 kills respectively. Timeout rates fell to 57.24% sampled and 60.84%
greedy. The gain therefore continues beyond the initial 10M jump, although it
has not yet reached the full-information pursuit baseline.

- continuation run: `learning-runs/sleep-explore-ring-v1-30m-corrected/`
- continuation evaluation: `results/sleep-explore-ring-v1-30m-corrected-fresh-test.json`

## 100M continuation

The valid 30M checkpoints were resumed to 100,007,936 decisions per seed,
with no task, observation, reward, or optimizer changes. The same fresh
2,048-episode suite gives the following three-seed means:

| total decisions | sampled clear | sampled kills | greedy clear | greedy kills | sampled timeout |
|---:|---:|---:|---:|---:|---:|
| 10M | 23.37% | 6.55 | 18.34% | 6.06 | 75.39% |
| 30M | 41.39% | 6.97 | 37.32% | 6.67 | 57.24% |
| 100M | **58.58%** | **7.28** | **56.67%** | **7.14** | **40.59%** |

The improvement continues through 100M: sampled clear rate rises another 17.19
percentage points from 30M, while the sampled timeout rate drops 16.65 points.
The three final sampled clear rates are tightly grouped (57.67%, 59.42%, and
58.64%), so this is not a single-seed effect. It is still well below the
full-information pursuit baseline (99.76% on this suite), which indicates that
the frontier ring makes local exploration learnable but does not provide the
long-horizon planning or global state needed for reliable completion.

- 100M continuation run: `learning-runs/sleep-explore-ring-v1-100m-corrected/`
- 100M fresh evaluation: `results/sleep-explore-ring-v1-100m-corrected-fresh-test.json`

## 300M single-seed continuation

To test whether the curve continues without paying for two more seeds, seed 0
alone was resumed from 100M to 300,023,808 decisions. The task, model, reward,
and optimizer were unchanged. On the same fresh 2,048-episode suite, seed 0
improved as follows:

| seed-0 checkpoint | sampled clear | sampled kills | greedy clear | greedy kills | sampled timeout |
|---:|---:|---:|---:|---:|---:|
| 100M | 57.67% | 7.28 | 56.49% | 7.17 | 41.55% |
| 300M | **65.82%** | **7.42** | **62.99%** | **7.28** | **33.45%** |

The additional 200M decisions therefore still produce a meaningful gain: +8.15
percentage points sampled clear and −8.10 points sampled timeout on the matched
seed-0 evaluation. The policy is still short of the 99.76% pursuit baseline,
but longer training continues to convert near-complete runs into clears.

- 300M single-seed run: `learning-runs/sleep-explore-ring-v1-300m-seed0/`
- 300M fresh evaluation: `results/sleep-explore-ring-v1-300m-seed0-fresh-test.json`
