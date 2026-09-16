# Separating encounter heuristics

Frozen 10M seed-0 rest/sleep model, sampled actions, no retraining. Same 1,024 initial validation episodes: 32 layouts × 32 placements, 24 ordinary enemies, 15×15 wall-blocked LOS, LOS-gated waking and 2,048 policy decisions. All interventions use observed information only.

## Components

- **Wait:** force wait when a visible enemy is awake and no visible enemy is adjacent.
- **Attack / model target:** whenever an enemy is adjacent, restrict the model distribution to legal adjacent-enemy attacks and sample from its renormalized probabilities. This forces attacking while preserving the model’s relative target preferences.
- **Attack / weakest:** whenever an enemy is adjacent, attack the lowest-HP one, with the original compass tie-break.
- **Retarget existing attacks:** if the model already selected an adjacent-enemy attack, change its target to the weakest adjacent enemy. Do not force an attack when the model selected movement or wait.
- **Retreat:** apply the original hallway retreat overlay to the otherwise selected action. It may override even an adjacent attack; destination, first-step-away restriction, blocked-route cancellation, hallway holding and encounter lockout remain unchanged. When combat resumes, control returns to whatever attack/model rule that arm uses.
- **Pursue sleepers:** if enemies are visible but none is adjacent or awake, replace the model action with the local observed-terrain pursuit rule. When no visible enemy is reachable, this rule can fall back to the frontier cue. This final addition reconstructs the prior full visible-trigger hybrid.

Composition priority: ordinary model or sleeper-pursuit action; waiting; adjacent attack rule; retreat overlay. Adjacent attacks and approach waiting are mutually exclusive. The model controls exploration and rest when no override applies. Memory is updated from observations throughout.

One categorical draw per batch row per decision is used in every arm. For model-target forcing, only the distribution at adjacency changes. All other overrides operate after sampling. Matching initial RNG does not preserve identical combat draws once trajectories differ.

## Results

| Variant | Clears | Deaths | Timeouts | Mean physical turns |
|---|---:|---:|---:|---:|
| model | 867 (84.67%) | 148 | 9 | 625.3 |
| wait | 894 (87.30%) | 118 | 12 | 672.9 |
| attack_model_target | 935 (91.31%) | 79 | 10 | 637.0 |
| attack_weakest | 954 (93.16%) | 57 | 13 | 648.1 |
| retarget_existing_attacks | 901 (87.99%) | 115 | 8 | 641.1 |
| retreat | 931 (90.92%) | 86 | 7 | 670.2 |
| wait_attack_model_target | 968 (94.53%) | 38 | 18 | 696.3 |
| wait_attack_weakest | 984 (96.09%) | 24 | 16 | 698.6 |
| wait_retreat | 938 (91.60%) | 74 | 12 | 710.4 |
| attack_weakest_retreat | 980 (95.70%) | 30 | 14 | 684.9 |
| wait_attack_weakest_retreat | 988 (96.48%) | 17 | 19 | 714.9 |
| full_visible_encounter | 1001 (97.75%) | 22 | 1 | 686.4 |

## Matched contrasts

| From → to | Net additional clears | Newly clear | Previously clear, now fails |
|---|---:|---:|---:|
| model → wait | +27 | 98 | 71 |
| model → attack_model_target | +68 | 133 | 65 |
| attack_model_target → attack_weakest | +19 | 58 | 39 |
| model → retarget_existing_attacks | +34 | 103 | 69 |
| model → retreat | +64 | 90 | 26 |
| attack_model_target → wait_attack_model_target | +33 | 57 | 24 |
| attack_weakest → wait_attack_weakest | +30 | 54 | 24 |
| wait → wait_retreat | +44 | 75 | 31 |
| attack_weakest → attack_weakest_retreat | +26 | 43 | 17 |
| wait_attack_weakest → wait_attack_weakest_retreat | +4 | 14 | 10 |
| wait_attack_weakest_retreat → full_visible_encounter | +13 | 24 | 11 |

## What this screen suggests

Forcing adjacent attacks while preserving model target preferences adds 68 clears (867→935). Weakest-target choice adds another 19 (935→954); changing targets only on attacks the model already selected adds 34 versus baseline (867→901). These contrasts support separate gaps in attack commitment and targeting.

Retreat alone adds 64 clears (867→931). Waiting plus weakest-target attacks reaches 984 clears without retreat. Adding retreat then brings only four more clears, while deaths fall from 24 to 17 and timeouts rise from 16 to 19. Thus retreat has a much smaller marginal clear-rate effect once these other rules are present.

Adding observed-terrain pursuit of sleeping-only visible enemies raises clears from 988 to 1,001, mostly by reducing timeouts from 19 to one, while deaths rise from 17 to 22. This is a completion-versus-risk tradeoff on this panel, not a pure combat-survival improvement.

These rules interact: their isolated benefits cannot be added together to predict the combined result.

## Validation and interpretation limits

Baseline and wait-only reproduce their saved clear/death/timeout rates, kills and physical turns exactly. Reconstructing the full visible-trigger hybrid reproduces those same metrics exactly. These checks connect this screen to the previous comparisons. Every selected action passed the original legal mask; every episode terminated. Target extraction checks cover adjacency, different HP, invalid directions and compass ties. Existing retreat and encounter-gate tests cover the reused components.

This is one model and a repeatedly used validation panel, with no untouched-test or statistical-significance claim. Contrasts estimate the effects of these specific evaluation-time rule changes, not a unique additive allocation of the full improvement. Interactions and trajectory changes matter. In particular, model-target versus weakest-target forcing compares two target-selection policies; retarget-existing-attacks provides a separate check without forcing the decision to attack.

Evaluation time across the 12 arms: 144.0 seconds. No training performed.

```sh
gpu-d1/.venv/bin/python gpu-d1/diagnostics/seek-destroy-los/run_components.py
gpu-d1/.venv/bin/python gpu-d1/diagnostics/seek-destroy-los/report_components.py
```

Raw episode outcomes, source hashes and checkpoint/library provenance: `results/los-encounter-components.json`.
