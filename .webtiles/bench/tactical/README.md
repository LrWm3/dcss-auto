# Tactical encounter lab (prototype)

This is a separate local initiative, not a port of dcss-ai-wrapper. Learned
policies remain experimental exports. The latest work also fixes a canonical
RC bug: do not enter shops while berserk or while visible enemies need combat.

## Configured dataset collection

`collect_cases.py` accepts a source RC/hash plus cases with main seed index,
visible monster name, floor, optional minimum turn, optional baseline warmup,
and a decision budget. It captures a private save, runs two reset baselines,
then independently launches the uninterrupted seed to the same trigger and
compares every normalized observation. A matching death alone is insufficient.

```sh
/usr/bin/python3 .webtiles/bench/tactical/collect_cases.py \
  .webtiles/bench/tactical/death-cases-v2.json \
  .webtiles/bench/tactical/artifacts/new-collection --jobs 3
/usr/bin/python3 .webtiles/bench/tactical/index_cases.py \
  .webtiles/bench/tactical/artifacts/new-dataset \
  .webtiles/bench/tactical/artifacts/new-collection
```

Destinations must be new. The index verifies checkpoint/RC/trace hashes and
exports only fidelity-passing cases, one baseline trajectory per case. Repeated
validation rollouts are not extra training examples. Split by **seed**, never
randomly by transition: first-contact, recovery, and critical checkpoints from
one encounter are correlated. No train/held-out generalization claim is made
for the already heavily tested five main seeds.

New captures save with an administrative `z` inside the existing ready/getch
boundary, avoiding a console round-trip. This is not a learner action. The save
clears the reported-observation latch so the loaded worker publishes its initial
state. Save/load fidelity remains case-specific: active berserk checkpoints can
repeat perfectly after load yet diverge from uninterrupted play. Such cases,
fresh-prefix divergences, missing encounters, errors, and incomplete capture
attempts are retained but excluded from the primary training file. `budget`
is never relabelled as victory. Transport verification does not by itself prove
equivalence to an earlier uninstrumented full-game death.

The initial configs deliberately freeze the full-five imitation-v2 source RC
to revisit those failures; they do not silently switch to newer production RCs.
Checkpoints include complete private save/RC snapshots and engine pins. Heavy
artifacts remain local under `artifacts/`; the tracked evidence index points to
them. No model has been retrained or promoted by this collection step.

`verify_stalls.py FIXED_RC NEW_OUTPUT` copies the saved seed2/seed4 stalls and
runs paired old/fixed private games, stopping intentionally at D:13. It does
not overwrite the original saves. `smoke_deployment.py --full --seeds 2,4`
runs fresh versions through death, a stall, or a bounded wall-clock budget;
without `--full` it retains the original D:5 smoke-test behavior.

## Current verified path (supersedes earlier imitation claims)

The old console-stepped **berserk** evaluations were not faithful to autonomous
play. Two observation mechanisms consumed gameplay randomness: extra input-cycle
preparation (`player_speed()` randomly rounds berserk timing), and character dump
generation. Replaying exactly the same actions without those mechanisms changed
the fight. The earlier non-berserk baseline equivalence remains valid; do not
reuse the old imitation model as evidence of autonomous performance.

The bench now reads action keys with `crawl.getch()` **inside ready**, without a
console round-trip or Lua macro delay. Structured dump sequence IDs are polled
from the private worker directory. Dump generation uses UI RNG in a separate
lab binary, `crawl-observation-rng`; the normal `crawl-webtiles` binary was not
replaced. Default lab engine is this corrected binary; `DCSS_TACTICAL_ENGINE`
can explicitly select another. Original saves, models, and engine pins remain
untouched. Administrative console calls are not the decision transport.

```sh
make -C crawl-0.35/crawl-ref/source WEBTILES=y GAME=crawl-observation-rng -j4 crawl-observation-rng
/usr/bin/python3 .webtiles/bench/tactical/autonomous_replay.py \
  --case .webtiles/bench/tactical/artifacts/observation-case-v1 \
  --reference .webtiles/bench/tactical/artifacts/observation-tactics-v1/worker-e32oafu0/transitions.jsonl \
  --output .webtiles/bench/tactical/artifacts/equivalence-repeat
```

The lab build includes the resume-greeting and character-dump patches under
`engine-patches/`. Tested SHA256:
`393c34054f447aa3dd94ae2b642462bbff34f0d50cb92c8b1fdec0432274d206`.
`migrate_transport.py` creates labelled copies with explicit RC/engine changes;
it never silently relaxes checksums. New checkpoint families, especially saves
during speed-changing statuses, still require their own fidelity verification.

Corrected adjacent-berserk demonstration: safe recovery in **70 decisions**.
Two automatic replays match **all 71 observed states**, without per-step dumps.
The exported disabled adapter matches all 41 baseline decisions from a fresh
game; the active adapter matches all 70 corrected demonstration decisions from
a fresh game. `models/eustachio-imitation-v2.json` is fitted from this new trace;
no RL improvement is claimed. The adapter reuses the canonical scan, rejects
unreachable/confused combat before Tab, and spends one wait then hands back if
an attempted action is rejected without consuming a turn.

Fresh uninterrupted smoke tests of seeds 1 and 3 both reached D:5. Seed 1 handed
off the unreachable target at2978, killed Eustachio under normal control at3259,
and reached D:5 at3740. Seed 3 killed Eustachio at3523, handed off after recovery
at3576, and reached D:5 at4681. These are **bounded integration tests, not full
five-seed progression benchmarks**. The two earlier smoke attempts incorrectly
treated a pattern-match timeout as a stall; they are harness failures, superseded
by v3's unchanged-output check.

[Tracked evidence](evidence/observation-deployment-v2.json),
[seed 1 dump](evidence/deployment-v2-seed1.txt),
[seed 3 dump](evidence/deployment-v2-seed3.txt).
`verify_deployment.py` reproduces the fresh comparisons; `smoke_deployment.py`
runs private two-seed games to D:5; neither changes existing live sessions.

## Run

Requires the corrected lab binary above and Python 3 with `pexpect` (available in
`/usr/bin/python3` on this machine). Run from the repository root:

```sh
/usr/bin/python3 .webtiles/bench/tactical/test_tactical.py
/usr/bin/python3 .webtiles/bench/tactical/bench.py capture \
  .webtiles/bench/tactical/artifacts/my-eustachio-case --warmup 35
/usr/bin/python3 .webtiles/bench/tactical/bench.py rollout \
  .webtiles/bench/tactical/artifacts/my-eustachio-case --action baseline --steps 140
/usr/bin/python3 .webtiles/bench/tactical/experiment.py \
  .webtiles/bench/tactical/artifacts/my-eustachio-case \
  --output .webtiles/bench/tactical/artifacts/my-experiment --episodes 8 --steps 140
```

Case and experiment destinations must be new; existing results are not replaced.
`--warmup` takes that many baseline decisions **after first Eustachio contact**,
before saving. The legacy CLI defaults to main seed 3 and Eustachio; use the
configured collector above for other seeds and encounters. All use MiBe.

## Environment contract

`Environment(workspace).reset(case_directory)` launches a private process from
an immutable checkpoint, checking engine/save/RC SHA-256. Each worker has its
own saves, macros, morgues, RC snapshot, and terminal transcript. `close()` stops
only that worker. Keep checkpoint directories when pruning worker artifacts.

`step(action)` returns the next observation and appends a transition. The initial
action set is eight movement directions, wait, Tab, adjacent-only autofight,
berserk, and one RC-controller decision (`baseline`). This is a **decision-level**
interface: Tab and RC decisions are macro-actions, not guaranteed single turns.
`turn_delta` records elapsed game turns; no-turn actions are not silently retried.

Observations use only CLua player-visible data: HP, statuses, visible relative
terrain/clouds, visible hostile monsters/threat colours, known inventory labels,
and recent messages. No hidden monster HP, hidden locations, engine RNG, or map
spoilers enter the policy. Collections are JSON objects with numeric-string keys,
not JSON arrays. The pilot has no recurrent memory and cannot solve general
invisibility tactics. Messages contain UI markup/noise; models should not assume
clean prose. Inventory letters are Crawl's category-specific selectors.

The Lua adapter is inserted into a snapshot of the canonical RC, reuses its local
visible-map scanner, and suppresses `ready()` automation between learner actions.
It serializes `BOT` as well as the production save globals. It uses character
dumps for structured transport, not fragile map-screen parsing. Console entry
requires a confirmed interpreter banner and a per-decision acknowledgement.
Sequence numbers reject redrawn historical readiness messages. A confirmed
read-only console probe handles commands that consume no turn and do not call
`ready()` again. Unexpected prompts/errors stop the trial, not count as deaths.

## Save/load fidelity

**Update: the observed first-contact divergence is fixed and verified.** The
resume-only god greeting consumed gameplay RNG through the weighted speech
selector, even for Trog's single greeting (default weight 10). The engine now
uses UI RNG for that resume greeting. New-game greeting draws are unchanged.
Two loaded replays and one fresh replay matched all 41 decisions of the original
uninterrupted trace, through death. This verifies this case, not every possible
save/location/status combination. The following describes the original finding:

**A save-loaded encounter is not yet proven equivalent to uninterrupted play.**
The fresh, stepped seed-3 trajectory reproduces the original Eustachio death.
But reloading the first-contact save changes the next monster action and outcome.
Repeated resets of that save agree with one another. Preserving `BOT` alone did
not fix the discrepancy; the resume greeting fix above was required.

Therefore these cases are labelled **save-loaded variants**, not exact historical
replays. The later critical case still has a reproducibly losing baseline, making
it useful for a small controlled experiment. Do not promote a policy based on
checkpoint success alone: replay the uninterrupted seed and then held-out seeds.

## Outcomes and learning

`experiment.py` compares RC, Tab, and a hand-written adjacent-berserk/Tab policy,
then performs a small tabular Q-learning run and two greedy evaluations. Q-learning
updates after each environment transition; this is online RL against a local
simulator, **not offline RL from a fixed dataset**. The transition dataset is a
foundation for subsequent offline work.

The Q policy chooses wait/Tab/one-step retreat/berserk using coarse HP, crowd,
distance and status buckets. It has epsilon-greedy exploration, alpha 0.3 and
discount 0.98; Python sampling seed is 0. This is only a plumbing smoke test.
Macro duration is logged but the current discount is per decision, not per turn.

- Death: observed engine death message; not a timeout.
- Safe recovery: no visible hostiles, engine says safe, full HP, no active status,
  poison or fire, sustained for at least 10 game turns. This is an observable
  safety proxy and can include escape; it does not assert Eustachio was killed.
- No-turn stall: eight consecutive decisions without turn advancement.
- Budget truncated: decision limit reached without another terminal condition.
- Harness error: unexpected prompt, timeout, engine error, or adapter failure.

Rewards: death -100, safe recovery +100, -0.1 per decision, -2 for a no-turn action,
and a small HP-fraction difference term. No kill reward encourages ignoring
lingering hazards. These reward weights and the coarse abstraction are provisional.
Current actions exclude consumable selection and targeted wands/throwing.

Artifacts include `run.json`, `transitions.jsonl`, `rewards.jsonl`, `result.json`,
`results.json`, `q.json`, terminal logs, and morgues. Early exploratory workers
predate `run.json`; their case metadata and frozen trial RC remain available.
Large artifacts are local and git-ignored. Small evidence summaries are tracked.
Identical reset evaluations test repeatability, **not generalization**.

Next: capture earlier losing decisions
with an uninterrupted replay fallback; expose consumables and safe action masks;
expand to multiple encounters with held-out cases before scaling training.

## First pilot results (2026-09-08)

Three local cases were captured: first contact (turn 3506, 56/56 HP), return after
teleport (3528, 42/56), and surrounded/critical (3541, 35/56). Two experiments
produced **24 episodes and 1,009 transitions**. See
[tracked evidence](evidence/initial-pilots.json) for hashes and worker paths.

On the critical save-loaded variant, RC baseline died in 3 decisions in both
repeats, and Tab also died in 3. The hand-written adjacent-berserk/Tab policy
recovered safely in 78 decisions. Q-learning found one safe recovery in 8
exploratory training episodes, but both subsequent greedy evaluations died.
The earlier return case's four training episodes and both greedy evaluations
also died. **No reliable learned improvement has been demonstrated.**

Repeatability checks compared normalized observations, not just final outcomes:
100 first-contact baseline decisions matched across resets; all 3 critical
baseline decisions matched. Median reset time was approximately 5.6 seconds in
the return pilot and 9.0 seconds in the critical pilot. These are local measured
times, not a throughput guarantee. No full five-seed benchmark was run here.

The RC-baseline return trials exhausted 180 decisions while continuing normal
play; they were not relabelled victories merely because the player remained
alive. Recorded death `final_turn` is the last observed decision boundary, not
necessarily the morgue's terminal turn. All worker artifacts remain local.

## Resume-greeting patch and verified case

The source change is in `crawl-0.35/crawl-ref/source/main.cc`; a portable copy is
tracked in [engine-patches/resume-greeting-ui-rng.patch](engine-patches/resume-greeting-ui-rng.patch).
No production RC change was needed. The patched binary is installed at the usual
`crawl-webtiles` path, SHA-256
`58edc03bb6522429a632fe4f7908997ef60316740942ef878e2e5cbd66b73556`.
The prior binary is preserved locally under `artifacts/engines/`, named with its
original SHA-256 `54cdf44895903fa3c7ac51278afff390d1bffe6f1abd581dc3529aa47a3d3b38`.
Running sessions were not restarted.

Old cases and pilot results remain untouched and pinned to the old engine. For
the patched engine, the verified first-contact case is
`artifacts/resume-rng-verification-v1/case`. Its save bytes and RC are unchanged;
its metadata explicitly records the engine migration. Return and critical cases
are now also verified (see below). Engine-hash enforcement remains enabled.

```sh
/usr/bin/python3 .webtiles/bench/tactical/bench.py rollout \
  .webtiles/bench/tactical/artifacts/resume-rng-verification-v1/case --steps 60
```

[Verification evidence](evidence/resume-rng-verification-v1.json) records all
three comparisons. `verify_resume.py` reproduces the check with explicit
`--engine`, `--case`, `--reference` (uninterrupted transitions JSONL), and a new
`--output` directory. It preserves original cases, creates a labelled migrated
case, compares player-visible observations excluding UI messages/sequence IDs,
and fails on any gameplay-state difference. The patch was built with
`make -C crawl-0.35/crawl-ref/source WEBTILES=y GAME=crawl-resume-rng -j4 crawl-resume-rng`
and installed by renaming the tested binary over the normal launch path.

## Faithful imitation experiment (2026-09-08)

[Evidence](evidence/faithful-imitation-v1.json) includes return/critical fidelity
checks, the faithful tactic sweep, and all imitation/RL evaluations. Return
(`artifacts/return-fidelity-v2/case`) matches 19 remaining decisions, critical
(`artifacts/critical-fidelity-v2/case`) matches 6; each passes two loaded runs and
one uninterrupted replay, all reproducing death.

On faithful first contact, RC dies after 41 decisions. Tab plus waiting recovers
in 180; charging with adjacent berserk recovers in 56. `learn.py` fits a small
tabular imitation policy from that successful trajectory. Both loaded evaluations
and an uninterrupted encounter evaluation recover in 56 decisions. Six online RL
refinement episodes yield five recoveries and one death; final greedy evaluations
also take 56 decisions. We selected imitation: refinement demonstrated no gain.
This is an in-sample result on one encounter, not a general tactical model.

```sh
/usr/bin/python3 .webtiles/bench/tactical/learn.py \
  --case .webtiles/bench/tactical/artifacts/resume-rng-verification-v1/case \
  --teacher .webtiles/bench/tactical/artifacts/faithful-first-contact-v1/worker-zwl_sc86 \
  --output .webtiles/bench/tactical/artifacts/imitation-rl-repeat --episodes 6
/usr/bin/python3 .webtiles/bench/tactical/export_model.py \
  .webtiles/bench/tactical/models/eustachio-imitation-v1.json \
  .webtiles/bench/tactical/artifacts/eustachio-imitation-repeat.rc
```

Output directories/files must be new. The Lua export activates only at Eustachio,
uses player-visible features, and hands back to the canonical controller after
safe recovery or on an unfamiliar state, floor change, or action/no-progress
budget. It respects pauses and logs activation, action changes, and handoff in
character notes. Production RC is not modified.

Paired full-game configurations are `../tactical-baseline-v1.json` and
`../tactical-imitation-v1.json`. They use the same five seeds and patched engine,
with separate frozen RC snapshots. Check their status through `../batch.py`;
the encounter stopping at safe recovery is not itself a full-seed result.

### Integration caveats found in the first full batch

Do **not** promote this export to production yet. Seed 1 selected Tab against an
unreachable Eustachio and stopped at the native `No reachable target in view!`
message. A repeated-ready no-op counter cannot protect an action that returns to
user input without invoking ready again. The adapter needs a pre-action legality
gate and rejection handling, with real-engine tests.

Seed 3 activated at turn 3506, selected berserk at 3508, and handed back on an
unseen model state at 3519. Eustachio died at 3523, but the canonical controller
later looped while berserk. This is not the 56-decision recovery seen in the
stepped evaluation, and the mismatch remains to be traced.

Other seeds diverged even without a recorded model activation. The current
wrapper performs an extra full scan before activation; its non-interference has
not been established. Do not attribute unrelated progression gains to the model.
Before further training, compare action/observation traces through a disabled
adapter, then through the deployed adapter, and eliminate these discrepancies.
Paused runs are recorded as paused, not deaths or successes.

## Automatic encounter mining

`mine_encounters.py` runs private baseline games from a JSON configuration,
discovers encounter boundaries, ranks candidates, recreates their starting
states, and builds a fidelity-gated dataset. It does not control live sessions,
change the production RC, train a model, or count losing actions as good advice.

```sh
/usr/bin/python3 .webtiles/bench/tactical/mine_encounters.py \
  .webtiles/bench/tactical/mining-v1.json \
  .webtiles/bench/tactical/artifacts/my-mining-run
```

Use a **new output directory** for each run. `mining-v1.json` is a short
30-capture infrastructure demonstration; `mining-deeper-v1.json` allows 2,500
decisions per seed to search farther for difficult fights. Seeds are arbitrary
uint64 strings, not restricted to the five main regressions. Configure `rc`,
`seeds`, `target`, `max_decisions`, `encounters_per_seed`, and `jobs`.
Optional `rc_sha256` rejects unexpected source changes. The engine is the
observation-RNG lab binary selected by `bench.py` / `DCSS_TACTICAL_ENGINE`.

An encounter starts when hostiles are visible and ends at full-health observable
safety, death, a floor change, or a labelled budget/stall. LOS breaks and
unfinished recovery remain part of the encounter. Floor changes are not wins;
timeouts and no-turn stalls are not deaths. Selection balances seeds and ranks
deaths, lost HP fraction, threat, and duration within each seed. Easy successful
fights remain comparison cases; there is no guarantee every selection is hard.
HP fraction is used because berserk changes maximum HP. This first version
does not separately detect resource spending or controller retreat decisions.
Passive `flying`/`parry` statuses do not prevent recovery; unknown statuses,
berserk/cooldown, confusion, poison, fire and missing HP still do. New enemies
on a destination floor belong to the new encounter, not the one just exited.

After changing ranking or segmentation, add `--reuse-discovery OLD_RUN` to
reuse its original traces. This verifies engine, source RC, observation/transport
code and trace hashes before re-segmenting. It still performs new checkpoint
captures and both reset checks. Discovery budgets in the new config do not
extend an already-recorded trace. This avoids rerunning full discovery games
just to experiment with candidate selection.

The collector verifies every visible observation in the discovery prefix while
replaying to a selected boundary, saves through the direct input transport, and
compares **two independent resets against the original discovery continuation**.
It checks the complete encounter, not only its outcome. Divergent cases stay
quarantined. Messages and transport sequence IDs are ignored; gameplay fields
are not. These checks establish visible baseline fidelity for this instrumented
environment, not equivalence to uninstrumented full-game play or determinism
for every possible alternative action.

Artifacts include:

- `manifest.json`, frozen `source.rc`, and `config.json`: version/hash provenance.
- `discoveries.json` and private worker `transitions.jsonl`: original evidence.
- `candidates.json`: priorities, enemy names, floor, HP loss, and trace offsets.
- `collection/encounter-NNN/case/`: immutable save/RC bytes and metadata.
- `collection/encounter-NNN/result.json`: checks and any rejection reason.
- `dataset/index.json`, `dataset/transitions.jsonl`: verified cases only, one
  baseline trajectory per case (verification repeats excluded).
- `summary.json`: discovered, selected, saved, verified, and quarantined counts.

The target counts saved encounters, **not guaranteed training-ready encounters**;
inspect the summary before training. All cases and repeats from the same seed
must remain in the same train/validation/test split. Related captures across
mining runs are not independent examples. Death trajectories are simulator
starting points for alternative-action search/RL, not imitation targets.

## Training on mined checkpoints

`train_encounters.py` is a separate, small **linear Q-learning** harness. It
leaves the legacy tabular trainer, exported models and production RC untouched.
It supports multiple verified cases, explicit seed-disjoint held-out evaluation,
and an explicitly labelled in-sample mode for debugging one encounter.

```sh
/usr/bin/python3 .webtiles/bench/tactical/train_encounters.py \
  .webtiles/bench/tactical/rl-d7-smoke-v1.json \
  .webtiles/bench/tactical/artifacts/my-d7-training
```

The D:7 config is a bounded pilot: six training episodes with two repeats of
the RC baseline, an adjacent-melee comparator, and the final frozen policy.
`rl-multicase-smoke-v1.json` exercises two training seeds and a separate
evaluation seed. These tiny runs test infrastructure, not generalisation.
To train longer, increase `episodes`; every invocation currently starts a fresh
model. Output paths must be new. `model.json` is retained after each episode;
it is **not compatible with the legacy Lua exporter**, and is not deployed.

Configuration selects a hash-pinned dataset index plus `train_cases` and
`eval_cases` using its case IDs. Only eligible cases with verified metadata and
matching save/RC/engine hashes are accepted. `held_out` mode rejects any seed
overlap, including different encounters from the same seed. `in_sample` is an
explicit exception and is marked throughout the reports.

The learner uses player-visible HP, nearby terrain/enemy geometry, threat counts,
statuses, recent HP loss, encounter age and peak threat. It does not use monster
hidden HP, true invisible positions, seed IDs or enemy names as policy features.
Actions are eight ordinary movements, adjacent melee without approaching,
berserk, wait, and one decision delegated to the RC (`baseline`). Delegation
can use the RC's consumable/routing logic; the learner itself cannot choose
inventory items yet. The conservative mask avoids known clouds/occupied or
unknown cells, confused movement and some immobilising statuses. It is not a
complete engine legality oracle; errors and no-turn stalls remain observable.

Reward (schema v2) is +100 for the miner's observable recovery condition, -100
for death, and zero otherwise. The old per-turn penalty favoured earlier deaths
among failed episodes and has been removed. There is no HP-gain, damage or kill
reward to farm. The supplied configs use gamma=1 so elapsed time alone does not
change terminal reward preference; optional discounting remains supported. Decision/turn
budgets bootstrap rather than pretending to be victories; floor exits and
no-turn stalls end the tactical task without a positive terminal reward.
Harness errors never count as deaths and stop the batch.

Recovery is a **proxy**, not proof that enemies died or that retreat will remain
safe. `handoff_steps` optionally continues the RC after an evaluation recovery,
reporting later death/floor change/bounded survival separately. These actions do
not update the model or earn learner reward. Their transitions follow the main
episode in the trace; only the tactical prefix has entries in `rewards.jsonl`.

Each output contains frozen config/manifest, full transition and reward logs,
per-episode outcomes/action counts/timings, a model snapshot, and a summary.
Inventory changes can be inspected in transition observations; automatic
resource-use aggregation is not implemented yet. Evaluation weights are checked
unchanged. Repeated resets are reproducibility checks, not independent samples.

### Fixed-tactic discovery before further RL

```sh
/usr/bin/python3 .webtiles/bench/tactical/sweep_tactics.py \
  .webtiles/bench/tactical/d7-tactic-sweep-v1.json \
  .webtiles/bench/tactical/artifacts/my-tactic-sweep
```

This compares RC, hold position, berserk-and-fight, visible-terrain retreat, and
retreat with a berserk commitment if blocked. Each fixed intention checks the
current state every decision. Retreat maximises visible enemy separation on
traversable tiles; it does **not** know where the last rest spot or entry stairs
are. Confusion/poison/fire delegate to RC, and no policy knowingly walks into
clouds. These are candidate teachers, not a newly trained model or production
changes. `d7-tactic-handoff-v1.json` audits the retreat variants with a longer
600-decision RC continuation after proxy recovery.

The sweep records separate initial outcomes and handoff outcomes; alive at a
budget is bounded survival, not a cleared encounter. Floor-change continuation
stops at the boundary and is not proof of clearing the new floor. Repeats of the
same checkpoint are in-sample reproducibility checks. Positive discovery alone
does not certify save/load fidelity for every alternative-action trajectory.
