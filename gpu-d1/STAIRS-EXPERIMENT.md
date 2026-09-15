# Three-stair voluntary exit experiment

Fresh seed-0 PPO policies, 30M decisions per arm, run sequentially: immediate, fully banked, half banked, quarter banked. All use the ordinary 256-layout training split and 32 validation layouts × 32 episodes, 24 normal enemies + 2 slow ogres, and a 1024-decision deadline. This is a toy extraction objective, not native Crawl scoring.

## Task

Every enemy kill counts equally. Killing the last enemy does not terminate. Action 9 descends from any of three distinct stair tiles and ends safely before monsters can retaliate. Entering a stair tile or waiting on it does not descend. Invalid descent acts as wait and is masked out for the policy. Death and timeout terminate with no bank payout. No clear bonus or exit bonus is paid.

One stair is at the player spawn; two are sampled on initially observed floor within Chebyshev distance 4, preferring unoccupied tiles. Stairs stay fixed during an episode; placement follows the existing per-episode random player spawn, rather than being fixed per layout. The placement RNG does not alter combat RNG. All reward arms have identical placements and dynamics under identical actions. Nearby floors may be separated by walls: these are floor tiles, not guaranteed direct corridors.

All three stairs use the same rules. Stairs are remembered via the existing seen-floor state. Nine appended features give each stair's known flag and relative coordinates. Two more give standing-on-stairs and pending bank divided by 26. Existing monster information and ring/frontier/route inputs remain; no required/optional role label is exposed. Observation width is 752, action count 10. There is no special stair route hint or hidden stair geometry input.

## Rewards

| Arm | Immediate reward per kill | Paid per kill on safe exit |
|---|---:|---:|
| immediate | 1 | 0 |
| bank_full | 0 | 1 |
| bank_half | 0.5 | 0.5 |
| bank_quarter | 0.75 | 0.25 |

Normal enemies and ogres both follow the same row. Already paid reward is retained after death. Pending bank is lost on death or timeout. Every action costs 0.001, death costs 1, and first-seen floor earns 0.002; the initial view earns nothing. These shaping rewards are identical across arms and are not banked. Empty descent earns no task reward (and pays the action cost). Exploration can still reward episodes with no extracted kills, so log the task metric separately.

Gamma 0.99 is unchanged. Banking therefore changes credit-assignment delay and discounted reward value as well as the risk of losing accumulated score. A weak full-bank result alone would not establish inability to judge risk.

## Outcomes

Primary selection metric: mean kills extracted safely per episode, regardless of the bank fraction. Report exit/death/timeout rates, total kills, ogre kills/damage/fatal blows, bank payout/forfeiture, empty exits, exits in ≤10 turns, HP/kills and enemies left by type conditional on exit, and exit frequency for each stair. `out[2]` now means exit; report keys use `exit_rate`. “Extracted kills” counts all kills from exited episodes, including the immediate arm, so task performance is comparable across arms. Native bank-payout values are not directly comparable across fractions.

Each checkpoint evaluates sampled and greedy policies and preserves per-map metrics. Best checkpoint selection uses extracted kills, then exit rate. An empty-exit policy cannot win selection merely by surviving. Fixed final checkpoints remain available for fair comparisons. One seed is a first screen, not a significance claim.

## Run

```sh
gpu-d1/.venv/bin/python gpu-d1/branches/stairs-v1/scripts/run_ring_ablations.py \
  --steps 30000000 --seeds 0 \
  --output gpu-d1/learning-runs/stairs-bank-screen-30m
```

The bounded runner keeps one resumable latest checkpoint and one compact best per arm, shares map files, caps suite storage at 2 GiB, and reserves 5 GiB free. It records actual training seconds separately from evaluation. Milestone evaluations are 0, 1M, 3M, 10M, and 30M; resume checkpoints are every ~1M decisions. The branch is isolated at `branches/stairs-v1` so historical tasks and checkpoints are unchanged.

Validation: `scripts/test_stairs.py SUITE` checks each compiled reward arm's native semantic assertions (all three stairs, banking, equal rewards by enemy type, no last-kill termination, invalid actions, death/timeout loss, observation gating), CPU/CUDA trajectories, and identical dynamics across reward fractions. Run `--smoke` first for end-to-end PPO, evaluation, and storage checks.

## Launch status

All four 512-decision smoke jobs completed. Native semantic tests and 8,400 CPU/CUDA world steps per arm passed (33,600 total), with matching state trajectories across reward fractions. The 120M-total-decision suite was launched in the background in the order above. Progress: `results/stairs-bank-screen-30m-console.log`; configuration: `results/stairs-bank-screen-30m-plan.json`; resumable suite: `learning-runs/stairs-bank-screen-30m`.
