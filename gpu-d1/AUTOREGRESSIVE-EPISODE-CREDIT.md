# Complete-episode credit diagnostic

Question: imitation already clears reliably, but PPO degrades it. Does credit
assignment through 64-decision bootstrapped GAE contribute to that degradation?
This test does not retain an imitation loss or add teacher overrides.

Start both conditions from the preserved original imitation checkpoint. Keep
+1 clear minus 0.00001 per physical turn, gamma=1, entropy=0, Adam .0003,
eps=1e-5, PPO clip [.8,1.2], four epochs, minibatch 4096, value weight .25,
gradient clipping .5, and the zero initial critic. Same observations/actions,
24 enemies, sleep, LOS, 2048 physical-turn limit, 256 training maps and the
existing one-third clump training distribution. REST pays every primitive turn.

Each update collects complete episodes from 64 parallel training worlds under a
frozen policy. Completed worlds are inactive; padded observations never enter
training. Fresh deterministic training seeds each update; the initial batch
must match exactly between conditions. Evaluate on validation only; no validation
transitions enter PPO. The only difference between the two new conditions is:

* `gae64`: lambda=.95 GAE, cut every 64 decisions with next-value bootstrap;
  critic target is GAE + old value, matching the historical estimator.
* `episode_return`: undiscounted reward from this state through the actual
  terminal outcome; advantage is this return minus the old critic prediction.
  Critic regresses the complete return throughout training, not just at startup.

Both normalize advantages over valid decisions. Complete sampled returns are
noisy estimates, not ground-truth action quality or counterfactual evidence.
They may positively reinforce mistakes in successful episodes.

This matched pair changes collection versus historical streaming PPO: full
64-world episode batches instead of 512 worlds x 64 decisions, with episode
resets between updates. Batch size and update frequency vary with episode length.
The comparison between the new conditions isolates the target estimator within
that procedure. Improvement in both could instead reflect collection or batching.
Runs finish whole batches after 1M valid decisions; report actual counts rather
than calling them exactly 1M. No partial episode outcomes are fabricated.

Diagnostics report actual/GAE target disagreement, normalized advantage sign
agreement, reversal-action credit, and post-update log probability changes for
positively/negatively credited actions and immediate reversals. Track approximate
KL, training turns/time, held-out sampled/greedy clears, deaths/timeouts, clear-only
turns, action counts, and episodes with >=8 consecutive reversals. Evaluate at
initialization, after the first update, around 250K/500K/750K on 128 placements
across 32 validation layouts, then on the full 1024-placement panel at completion.
Small intermediate and large final panels must not be compared as identical sets.

Synthetic tests check terminal boundaries, exact chunk bootstrapping and GAE
against an independent forward-sum implementation. Native runs assert complete
termination, legal actions, actual episode return identities including REST,
MC start returns equal accumulated episode reward, and old policy log probabilities
match before optimization. Smoke test performs both real PPO conditions and
held-out evaluations, including identical first collected batches.

Run with `gpu-d1/.venv/bin/python
gpu-d1/diagnostics/autoregressive-imitation/episode_credit.py` from repository root.
`--smoke` uses eight training worlds and one update per variant. Results:
`results/autoregressive-episode-credit.json`; checkpoints in ignored
`learning-runs/autoregressive-episode-credit`. Only compact milestone weights and
one latest optimizer checkpoint per condition are retained; no trajectory dumps.
2 GiB output cap and 10 GiB free reserve. Latest checkpoints are diagnostic
artifacts, not a promise of exact mid-experiment resumption. Source/checkpoint
hashes and the reference job are included in results. One seed, preliminary test.

## First launch interrupted and restarted

The first full launch stopped collecting its second training batch: reverse MC
summation differed from forward reward accumulation by 2.115965e-5, exceeding
the 2e-5 assertion tolerance. This is float32 accumulation-order error across a
long successful episode, not evidence of incorrect terminal rewards. The native
reward-versus-physical-turn check had passed. Preserved partial results:
results/autoregressive-episode-credit-interrupted.json.

The restart changes only that comparison tolerance to 1e-4; it does not change
reward calculation, target calculation, PPO settings or either estimator. A
2048-step synthetic success test now explicitly checks reverse/forward sums
against each other and against a float64 reference. Other assertions remain.

Before interruption, the first GAE control update (33,733 decisions) reduced
greedy clears on 128 diagnostic placements from 120 to 6; sampled clears changed
124 to 125, and successful sampled completion time rose from 687.7 to 808.7 turns.
There was no full-return result yet, so this is not an estimator comparison.

## Completed matched comparison

Both variants completed after the rounding-check fix. Final validation uses the
same 1024 placements as prior full-panel evaluations; initial imitation had
992 sampled and 967 greedy clears. Each intermediate panel had only 128 episodes.

| Variant | Decisions | Updates | Training seconds | Sampled clears/deaths/timeouts | Greedy clears/deaths/timeouts | Sampled clear-only turns |
|---|---:|---:|---:|---|---|---:|
| GAE64 | 1,030,053 | 26 | 128.12 | 983 / 37 / 4 | 195 / 20 / 809 | 800.40 |
| Full episode return | 1,047,124 | 20 | 134.59 | 900 / 27 / 97 | 0 / 19 / 1005 | 1229.52 |

Total wall time 415.55 seconds (6.93 minutes), including validation. Actual budgets
overshoot to finish complete batches. Slower full-return episodes mean larger
batches and fewer updates under the matched collection rule.

After the identical first 33,733-decision batch, full-return greedy clears were
115/128 versus 6/128 for GAE (initial 120/128). This early preservation did not
last: at ~291K full-return greedy clears were 13/128, and at ~768K they were zero.
Final GAE greedy timeouts with >=8 consecutive reversals: 806/809; full-return:
981/1005. Sampled mean MOVE decisions were 483.01 versus 982.79. Full-return
sampled reward .866136 was lower than GAE .952132 under the same objective.

Using observed complete returns therefore does not fix deterioration in this
setup; at ~1M it is worse for both greedy and sampled success and completion time.
This weakens a simple explanation based solely on a short rollout's missing
terminal rewards, not every possible credit-assignment explanation. MC returns
can reinforce detours in successful episodes; neither estimator measures the
counterfactual benefit of each action. Both actor advantages and critic targets
changed together, so this experiment does not isolate actor loss, critic-induced
shared-feature drift, or update size as the remaining cause. Mean old-value and
sampled-return estimates in the final full-return training batch were .9106 and
.9082 respectively, but matching these means does not establish critic accuracy
or correct action ranking. One seed; no claim of universal estimator superiority.
