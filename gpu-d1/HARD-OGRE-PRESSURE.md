# Close, awake ogre diagnostic evaluation

Evaluation only: no training, demonstrations, or reward changes. All policies use final (`latest.pt`) checkpoints and the observation label setting they were trained with.

## Protocol

48 frozen scenarios on 12 loop geometries, disjoint from the original pressure training and validation geometries up to translation, rotation, and reflection. Each geometry has four cases: initial ogre distance 3 or 5, and initial energy 70 or 75. Ogres start awake. Corridor widths are 2 or 3 tiles; the single required enemy starts beyond the ogre. Player stats, enemy stats, actions, rewards, and 1024-turn deadline are unchanged.

Each policy/control gets 32 sampled episodes per scenario (1,536 episodes). Geometry variants share layouts and are not independent maps. All models are training seed 0. This is an exploratory diagnostic suite, not a new independent confirmation of label/feature effects. Known global monster positions, monster type, and fixed enemy slots are still available.

A full-map avoidance controller cleared all 192 witness episodes (four per scenario) without ogre damage and with the ogre alive. This demonstrates feasible behavior on those sampled episodes; it is not a proof of universal avoidability. No cases were removed based on policy or witness results.

## Results

| Policy / control | Clear | Any ogre damage | Ogre fatal blow | Mean turns |
|---|---:|---:|---:|---:|
| ordinary_50m_label | 99.61% | 2.47% | 0.39% | 27.4 |
| pressure10_50m_label | 99.80% | 1.63% | 0.20% | 26.0 |
| ordinary_50m_no_label | 99.48% | 1.24% | 0.46% | 28.8 |
| ordinary_150m_label | 99.80% | 1.17% | 0.20% | 27.1 |
| random_legal | 2.28% | 99.61% | 97.07% | 20.5 |
| required_monster_chase | 61.72% | 81.97% | 36.85% | 9.4 |

All trained-policy clears left the ogre alive; no ogres were killed by any tested policy/control. Random chooses uniformly among legal actions. Direct chase minimizes next-step Chebyshev distance to the required monster, breaking ties randomly, without looking at the ogre. It is a deliberately simple control, not an optimal hazard-blind planner.

## Disengagement

An episode qualifies as exposed when an awake ogre is within distance 3 after a player action and before monster actions. Damage-free disengagement means subsequently reaching distance at least 5 while alive, with the ogre alive and no ogre damage taken yet. Terminal-reset observations are excluded. This is a behavioral proxy, not a claim about policy intent. An episode can qualify and later die.

| Policy | Exposed episodes | Damage-free disengagement, conditional on exposure |
|---|---:|---:|
| ordinary_50m_label | 65.6% | 92.9% |
| pressure10_50m_label | 59.0% | 93.6% |
| ordinary_50m_no_label | 63.5% | 95.8% |
| ordinary_150m_label | 78.8% | 96.2% |

Exposure rates differ by policy, so conditional disengagement percentages do not compare identical subsets. Unconditional counts/rates and per-scenario results are in results.json.

## What this establishes

Trained policies can handle a nearby, awake, optional slow ogre on these novel small loops. Success is much higher and damage much lower than random actions or direct pursuit of the required enemy. Ordinary training sufficed, including for the policy trained without the explicit role label.

The suite still has a ceiling for trained policies, so it does not resolve which features or curriculum are better. Closing the spawn distance alone does not reproduce the ordinary-floor failure mode. A better next diagnostic is multi-enemy interference on these same layouts, or replaying actual ordinary-floor failures; full-floor deaths need not imply inability to perform simple disengagement.

## Validation and runtime

CPU/CUDA observations, action masks, and outputs matched for 3,072 world steps per label setting on the new maps. The two historical 50M original-pressure clear rates reproduced exactly (99.8047% ordinary-only, 99.4141% pressure-trained).

Measured policy and control rollout time: 1.3s; CPU witness rollout: 0.5s. These exclude map generation, compilation, model loading, and environment construction. Training time: zero.

## Reproduce

From repository root:

```sh
gpu-d1/.venv/bin/python gpu-d1/branches/ogre-pressure-v1/scripts/evaluate_hard_pressure.py
```

Scenario metadata and ASCII previews live in `branches/ogre-pressure-v1/fixtures/pressure-hard-test/`. Native map caches (~61 MiB) and evaluation libraries are regenerable and ignored. Compact per-scenario results and checkpoint hashes live in `results/hard-ogre-pressure/results.json`.
