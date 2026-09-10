# General-policy foundation: 2026-09-10

The previous smoke established transport and orchestration, but did not establish
the requested general learning capability. This follow-up found and corrected:

- a teacher that oscillated instead of routing through remembered terrain;
- stale remembered monsters advertised as adjacent melee targets;
- a stair-delay handoff that blocked on terminal input;
- behavioral cloning of the learner's own mistakes and reinitializing candidates;
- overlapping training/evaluation seeds and promotion on a turn-count proxy;
- treating unfinished counterfactual continuations as progression rewards;
- missing official morgue score parsing and missing credit for earlier decisions;
- resume cycle counters lost when interrupted outside the idle phase.

The current teacher produces ordinary exploration, melee, recovery and stair
demonstrations. The general neural network receives candidate-relative route
distance changes, local terrain/monster geometry and an explicit full-health
indicator. These are state/action features; the policy still scores every
advertised action and receives no teacher override at execution time.

Actors retain teacher corrections on their own visited states. Candidates start
from the champion, learn these corrections, and receive log-scaled official
final-score targets from completed episodes. Unfinished episodes/branches have
missing return targets rather than synthetic score rewards. Promotion requires
at least five complete paired games and a positive paired-bootstrap lower
confidence bound for mean score improvement. Five games is a minimum guard,
not a claim of robust statistical power.

## Recorded results

The teacher on training seed 1760771545328102754 reached D:3 and died to Ijyb:
1,051 decisions, official score 49 (confirmed in Crawl's seeded xlog).
The first stair attempt had exposed the fixed transport bug; its failed trace
is retained in `artifacts/navigation-v2`.

A neural model trained on that teacher run and corrections from a separate
training rollout was tested on three fresh evaluation seeds. No data from these
evaluation games was fitted. All variants here are exploratory validation,
not a final untouched research test suite.

| Seed suffix | Neural | Random legal actions |
| --- | --- | --- |
| 011 | D:1, truncated at 1,500 actions | D:2, truncated |
| 012 | D:1 death, score 3, 44 actions | D:1 death, score 0, 1,091 actions |
| 013 | D:2 death, score 41, 740 actions | D:1, truncated |

The neural D:2 run selected 457 movements, 54 melee actions, 228 waits and one
descent. It received no scripted action overrides. This establishes some basic
general play; it does **not** establish mean-score superiority over random or
autonomous training improvement, because several runs are censored/truncated.
An earlier representation frequently waited forever at full health; those
negative results remain in `artifacts/competence-v3`.

Artifacts: `artifacts/competence-v4/results.json`; the tested model is
`artifacts/navigation-v3/route-deltas.pt`. It uses feature version
`general-features-v4-route-deltas`; earlier models are rejected on load.

Seven focused tests pass, and real-engine snapshot/replay determinism passed
in `artifacts/determinism-foundation-v4`. A two-cycle unattended smoke completed
with 60 actor actions, 64 replay rows, four counterfactual records, two paired
evaluations and zero recorded failures. No challenger was promoted.

## Larger run

`artifacts/foundation-general-training-v4` was launched with five bootstrap
seeds, 2,000-action limits, three actors per cycle, five evaluation pairs,
two requested cycles and 2,000-action counterfactual continuations.
It may take substantial time to complete. Inspect current state with:

```sh
./train_crawl_agent --run-dir .webtiles/bench/autonomous/artifacts/foundation-general-training-v4 --status
```

## Readiness boundary

There is now enough foundation for useful general-policy training experiments:
ordinary teacher trajectories, a neural policy that can reach another floor,
corrections on its own state distribution, actual-score learning and guarded
evaluation. The larger run still has to demonstrate improvement.

The boss's full V1 acceptance remains open. In particular: broad consumable,
spell and target validation; complete legal-action coverage (the Lua adapter
still has an 88-action limit and targets several actions at the nearest enemy);
robust recovery from every learner/checkpoint failure; long unattended operation;
and a convincing held-out improvement over the initial general policy. The
archive is currently a small floor/combat sample, not a learned frontier
curriculum. Truncated counterfactuals provide no score supervision yet.
