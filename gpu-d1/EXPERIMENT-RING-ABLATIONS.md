# Ablation program for the corrected ring task

Status: proposed experiments, not launched. Baseline is the corrected
40-enemy ring task, 1024 decisions per episode, 256 training maps, PPO with
two 128-unit hidden layers, and training seed 0 for the initial screen.
All modifications below require fresh training unless explicitly described as
checkpoint evaluation or continuation. Compare each modification with its
unchanged parent configuration at the same training budget.

## What the existing result establishes

At 10M decisions, the single-map policy clears its original map in 30.37% of
fresh evaluation episodes, but neither policy clears any validation episode
in the matched panel. On validation, multi-map training gives 11.04 kills per
episode versus 7.95 for single-map training. Multi-map kills on its training
panel are similar (11.38), with 0% clears there too.

This shows weak clearing performance at this budget. It does not identify a
network capacity limit, prove that longer training will work, or locate a
particular learning threshold. The single-map drop is evidence of poor transfer;
the data do not by themselves reveal the mechanism of specialization.

## Prerequisites and common measurements

These are correctness and measurement work, not ablations:

- Finish explicit tests of all 40 observation slots, dead-monster slots, player
  fields, every map ID, largest distance offsets, connected spawns, and memory
  clearing on reset. The last run's short parity checks are useful but do not
  establish all of these properties. CPU/GPU parity can share a semantic bug.
- Freeze the current environment and checkpoint compatibility information;
  record observation schema, build flags and library hash, all source hashes,
  map IDs, geometry hashes, resolved player/enemy configuration, and PPO settings.
  Correct the single-map wrapper's stale revision label in future metadata.
- Add terminal metrics for revealed floor, physically visited floor, action
  counts, enemies still asleep, and causes of stalls. They were proposed in the
  previous design but are absent from the current matched evaluation output.
  Add training episode/reset and decision counts per map, policy entropy,
  value error, approximate KL, clipping fraction, and gradient norms.
- Keep the 256/32/100 map split. Use balanced per-map evaluation episodes with
  both sampled and greedy actions. Use a fixed fresh episode bank and repeat
  finalists on another bank. Preserve the original 32-map panel for continuity;
  it was selected by evenly spaced map IDs, not a verified geometry-diversity
  algorithm. Stratify by map size, branching, corridors, and monster density.
- Report means across maps and uncertainty across maps and training seeds.
  Sixty-four episodes on a map are not sixty-four independent layouts. Start
  with one seed for screening; repeat promising changes and their controls on
  seeds 1 and 2. Extend replication if effects remain uncertain.
- Keep clears as the primary task outcome, with kills, death/timeout rates,
  coverage, and learning curves as diagnostics. Raw shaped return cannot rank
  experiments that change rewards. Lower enemy counts and longer deadlines
  define different tasks; evaluate candidate curricula back on 40/1024.

Current observations reveal every living enemy's location and HP globally.
Local terrain is a 9x9 square, including cells behind intervening walls, with
a remembered 11x11 outer ring. There is no general recurrent state. This is
the toy task being tested; changes to enemy visibility are a separate branch.

## A. Learning budget and map distribution

| ID | Change | Question and interpretation |
| --- | --- | --- |
| A1 | Continue existing 256-map run to 30M, then 100M; retain 10M checkpoint | Is the current learning curve simply slow? Continuation is the cleanest first intervention. Do not assume 0% clears at 10M is a plateau. |
| A2 | Nested map sets of 1, 4, 16, 64, 256; screen 16 and 64 first at 10M | How rapidly does learnability deteriorate with diversity? Use the same multi-map implementation for every condition. Include 1057 in the nested set for continuity and repeat with other subset selections before claiming a universal map-count effect. |
| A3 | Several different single-map references, selected before looking at learned scores | Was map 1057 unusually easy or unusually amenable to the existing representation? Existing pursuit results already show its difficulty differs from the average validation layout. |
| A4 | Compare equal total decisions with a small exposure-matched study | Does performance track experience per map? Use 4 maps at 10M versus 16 maps at about 40M as an initial example, logging actual decisions and resets per map. This also changes total optimization budget, so interpret together with A1/A2. |
| A5 | Curriculum 16→64→256 versus 256 throughout, equal total decisions | Does learning reusable behavior on a smaller map set ease later training? Include all phases in the budget; evaluate every phase on the same validation maps. |
| A6 | Uniform map choice per reset versus balanced allocation of training decisions | Are short episodes on difficult maps distorting actual exposure? Uniform resets do not imply equal decision counts. Run only if exposure logs show a consequential imbalance. |

## B. Terrain information and memory

| ID | Change | Question and interpretation |
| --- | --- | --- |
| B1 | Retrain without absolute player x/y; retain relative enemy locations | Are absolute coordinates encouraging map-specific rules? Zero these channels in a fresh run to keep input width constant. Existing-checkpoint masking is a reliance probe, not the training ablation. |
| B2 | Ring input present versus zeroed, with exploration reward unchanged | Does the remembered perimeter contribute useful information? Decouple observation removal from reward removal. |
| B3 | Remembered ring versus corrected known-terrain frontier versus both | Is a compact long-distance exploration target more useful than the local perimeter? Define frontier anchors as known floor next to unknown; choose and route through known traversable cells only. The old frontier code uses true-map distance fields and is a distinct privileged condition. |
| B4 | Ring versus a larger remembered-terrain patch, initially 21x21 | Is memory beyond one step's perimeter useful? Encode unknown=0, known wall=-1, known floor=+1; never fill unknown cells from the true map. A flattened larger patch also adds parameters; provide a size-matched control when attributing gains. |
| B5 | Feedforward policy versus GRU memory; short frame stack as a cheaper preliminary check | Must the agent remember routes or failed attempts that its current observation cannot distinguish? Give the recurrent model previous action/reward, sequence training, episode resets, and a feedforward control of comparable size. |
| B6 | Full remembered map versus full true map, with otherwise identical spatial encoder | Is the bottleneck access to route information? The remembered map must hide unrevealed terrain. The true-map version is a privileged diagnostic, not a fair information-matched improvement. |
| B7 | True-map next-step direction to nearest enemy, compared with target bearing alone | Does supplying route computation make the task readily learnable? Distinguishes global target localization (already present) from navigating around walls. This is a privileged oracle feature with no demonstrations required; compare to actual-path pursuit separately. |
| B8 | Separate visited-floor history from revealed-floor history | Does the agent benefit from distinguishing passing through a square from merely seeing it? Add a physically visited channel, preserve first-seen reward. Test visited reward separately in D3. |

B6/B7 are diagnostics that add information or computation. Success would show
that those aids help, but not that missing information is the sole cause of
failure. Failure would not by itself rule out an implementation or optimization
problem. The scripted pursuit reference is information-advantaged, not a bound
on optimal performance or a consistently stronger training teacher.

## C. Representation and model size

| ID | Change | Question and interpretation |
| --- | --- | --- |
| C1 | Two hidden layers of width 128→256, then 512 only if useful | Is the baseline too small at the same information level? Compare both decision budget and elapsed training time. Larger models also change optimization, so improved performance is not proof of one specific cause. |
| C2 | Small convolutional terrain encoder versus flattened terrain | Would shared spatial pattern processing help on unfamiliar maps? Keep enemy/scalar branches and input information unchanged; compare roughly matched parameter counts. |
| C3 | Shared enemy encoder with pooling/attention versus 40 fixed slots | Can the policy learn rules about monsters independent of their list position? First evaluate robustness to whole-record permutations, then retrain with permutations; do not reorder simulator entities or alter their stats/tie-breaking. |
| C4 | Explicit enemy HP, damage, speed, hit-related stats, awake state and action timing versus current ordinal type feature | Is the current monster encoding hiding useful tactical facts? Extract actual proxy values; test the richer representation with fixed distributions before varying stats. |
| C5 | Clock encoded as ticks/1024 versus ticks/256 | Does feature scaling help optimization? The current 0..4 clock is not inherently a semantic error; hold the 1024 deadline fixed. |
| C6 | Train-time translation/reflection augmentation after symmetry tests | Does reducing reliance on layout coordinates help? Transform terrain, enemies, memory, player coordinates and action labels consistently. Do not assume native movement tie-breaking is exactly reflection-invariant. |

## D. Rewards and credit over time

Current undiscounted episode return is approximately
`kills + 3*clear - death - 0.001*turns + 0.002*newly_seen_floor`.
The initial view receives no exploration reward. Clearing is our outcome metric,
but this reward also values partial kills and survival duration differently;
the two objectives need not prefer the same policy.

| ID | Change | Question and interpretation |
| --- | --- | --- |
| D1 | First-seen reward 0, 0.001, 0.002 (current), 0.004; start with 0 | Does the current bonus help, distract, or have little effect? Keep ring memory active when setting reward to zero. Inspect coverage and the reward components separately. |
| D2 | Exploration reward on/off × ring input on/off | Does memory make the shaping signal useful? Complete the 2×2 only after B2/D1 so it reuses their results; do not infer the interaction from isolated historical runs. |
| D3 | Reward first physically visited floor instead of first revealed floor | Does reward for entering cells better align with useful movement? Hold memory constant. Include a reward-scale control because far fewer visited than revealed cells may be counted. |
| D4 | Clear bonus 3→10, separately death penalty -1→-5 | Are profitable partial kills being favored over finishing? These intentionally change incentives. Compare clears, deaths, kills and covered floor, never raw return across variants. |
| D5 | Step cost -0.001→0, with every other reward fixed | Is the time penalty discouraging useful detours or resting? It could also promote waiting; diagnose actions rather than assuming a direction. |
| D6 | Discount gamma 0.99→0.995, then 0.999 if needed | Is distant completion too weakly valued relative to immediate kills? Higher discount can make value estimation harder; inspect value diagnostics and keep PPO rollout size fixed initially. |
| D7 | Potential-based shaping on remembered coverage versus raw first-seen bonuses | Can shaping speed learning without changing the underlying base-return objective? Use `gamma*Phi(next)-Phi(current)` on the augmented state with memory/time and zero terminal potential. This preserves the base objective under the theorem's conditions, not pure clear probability or guaranteed PPO convergence. |

## E. Combat and exploration isolation

These diagnostic tasks intentionally alter the game. They locate difficulty;
their scores are not directly comparable with the unchanged task.

| ID | Change | Question and interpretation |
| --- | --- | --- |
| E1 | Enemy count 8, 20, 40 at fixed stats/map/budget | Is clearing failing because of encounter load? Fewer enemies also reduce density and kill-reward frequency, potentially making navigation harder. Track both effects and keep unused slots masked. |
| E2 | Sleep enabled versus all monsters awake from reset | Does delayed discovery/engagement create the difficulty? Awake monsters approaching the player change route demands and combat pressure simultaneously. |
| E3 | Player takes no damage; keep monster locations/movement and attack effort | Can the policy locate and finish targets when mortality is removed? This separates survival from navigation more cleanly than lowering enemy count. |
| E4 | Compact combat arena with the same stats and actions | Can the policy learn melee, retreat and resting when long navigation is absent? Test across placements; success does not establish full-floor play. |
| E5 | Navigation-only target task on the same floor geometry | Can it reach an indicated destination around walls without combat? Use a goal coordinate, terminal arrival reward, and the same terrain memory. Avoid zero-enemy auto-clear; this needs a separate termination rule. |
| E6 | Training deadline 1024→2048, with matching time features | Is there simply insufficient episode time? Evaluate existing checkpoints at longer deadlines first as a probe, recognizing their clocks extend beyond training support. Retraining tests adaptation; evaluate candidates at the original deadline too. |
| E7 | Fixed stats versus bounded player variation, then bounded monster variation | Can a useful policy condition on strength/speed? Perform after C4 and meaningful fixed-stat learning. Test in-range variation and held-out combinations separately; change player and monster variation in separate arms. |
| E8 | Global enemy records versus currently visible records plus last-seen memory | How much does privileged enemy revelation help? This is a new information regime, requiring fresh training and a fair baseline. Defer until the present task learns. |

## F. Optimization and action selection

| ID | Change | Question and interpretation |
| --- | --- | --- |
| F1 | Greedy, sampled, and sampled temperatures 0.5/1/1.5 on existing checkpoints | Is stochastic action selection escaping loops? No new training. Choose any deployment temperature on validation, and report performance as policy-plus-decoder. |
| F2 | Entropy coefficient 0, 0.003, 0.01 (current), 0.03 | Is PPO becoming too deterministic or staying too diffuse? Run only after examining entropy and trajectory loops; entropy bonus is not the same as decode temperature. |
| F3 | Learning rate 1e-4, 3e-4 (current), 1e-3 | Is the apparent learning limitation an optimization issue? Use value/KL/clipping diagnostics to prioritize, not an exhaustive blind sweep. |
| F4 | Rollouts 64×512 versus 256×128 (32,768 decisions per update) | Does longer contiguous experience help? This trades parallel worlds for trajectory length; disclose that tradeoff. Keep update count, epochs and minibatch size fixed. |
| F5 | GAE lambda 0.95→0.99 | Does retaining longer reward traces help? Change separately from rollout and gamma, then test their interaction if supported. |
| F6 | Small weight decay/other regularization | Does the model overfit once it performs well on training maps? Low priority while both training and validation clearing are near zero. |

Do not start by changing PPO to another algorithm, adding search, or expanding
ring sizes by one tile. Those either change too much at once or address a lower
priority uncertainty than budget, memory, incentives and navigation.

## Recommended execution order and budget

1. Finish measurement/correctness prerequisites. Evaluate existing checkpoints
   with fresh episodes, per-map trajectories and action-temperature probes.
2. First screen: continue the existing 256-map seed-0 baseline to 30M (20M
   additional decisions); train six new seed-0 variants to 10M each: 16 maps,
   64 maps, no absolute coordinates, no exploration bonus, ring plus a frontier
   routed only through known floor, and width 256. Total: about **80M new
   decisions**. This reuses the existing 10M control for the 10M variants.
3. Continue the unchanged baseline to 100M before declaring a plateau (another
   70M decisions). Use its 30M and 100M curves to choose equal-budget follow-ups
   for promising candidates. Total for this screen plus baseline extension:
   **150M additional decisions**, excluding any candidate extensions.
4. Use E3/E5 and B6/B7 as targeted diagnostics if all candidates still stall.
   If a navigation/memory aid helps, test recurrence/spatial encoders next. If
   survival dominates, test combat isolation and incentives. If familiar-map
   performance improves but validation does not, prioritize representation,
   diversity and generalization controls.
5. Replicate the most informative two candidates plus their common control
   with seeds 1 and 2. At 30M each that costs another **180M decisions**; at
   10M each, **60M**. Select the budget from the observed curves. Replicate
   map-subset selection for conclusions about map count.
6. Combine only supported changes, then remove each component from the combined
   candidate to check whether it still helps. Use the reserved 100 test maps
   only after selecting the setup on validation.

At the last measured baseline throughput (~187k decisions/s), 80M and 150M
would take roughly 7 and 13 minutes of training-only time if throughput stayed
constant. These are reference calculations, not wall-clock commitments: new
architectures, known-map frontier computation, implementation, loading and
balanced evaluation can cost substantially more. In the previous run, balanced
per-map evaluation alone took about three minutes. Benchmark each new variant.

## Research basis

The choices above are hypotheses for this proxy, not published claims that
these settings will solve it. Map-count, generalization and model-size studies
are motivated by [Procgen (Cobbe et al., 2020)](https://proceedings.mlr.press/v119/cobbe20a.html),
which studies sample efficiency and held-out levels and reports benefits from
larger models. [CoinRun (Cobbe et al., 2019)](https://proceedings.mlr.press/v97/cobbe19a.html)
shows why large training sets alone do not establish generalization and
motivates testing representation and regularization.

The reward-shaping distinction comes from [Ng, Harada and Russell (1999)](https://people.eecs.berkeley.edu/~russell/papers/icml99-shaping.pdf):
arbitrary bonuses can alter the optimal policy, whereas correctly constructed
potential-based shaping preserves the underlying discounted objective.
The replication and uncertainty protocol follows the concern established by
[Agarwal et al. (2021)](https://proceedings.neurips.cc/paper/2021/hash/f514cec81cb148559cf475e7426eed5e-Abstract.html)
about drawing conclusions from a few noisy RL runs.
