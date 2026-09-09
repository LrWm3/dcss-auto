# Encounter augmentation pilot

This pilot creates ten synthetic variants of each of six inspected encounters:
Jeremiah, Maggie, Eustachio, the D5 ogre fight, D2 gnolls, and the D5 centaur.
It does not train a model or alter production games.

## Mechanism

`augment_encounters.py` makes recipe-backed checkpoints: an unchanged, hash-pinned
parent save plus a derived RC that applies its recipe once per process, before
the first observation. These are not binary-edited saves. Resetting the same
variant reapplies the same transformation to the same original save, never to
an already transformed state.

The separate `crawl-tactical-augment` engine adds an opt-in `you.tactical_augment`
binding. It changes only current HP and advances the gameplay RNG by a bounded
number of draws. It does not reseed the dungeon, reveal the map, move monsters,
alter equipment, advance a game turn or clear status effects. The hook requires
`DCSS_TACTICAL_AUGMENT=1`; ordinary games do not enable it. Source patch:
`engine-patches/tactical-augmentation.patch` (apply in Crawl's source directory
on top of the existing observation/resume RNG patches).

The ten recipes are explicit in `augmentation-pilot-v1.json`: 100%, 80% and
60% starting HP with selected gameplay-RNG offsets. HP is floored, minimum one.
RNG offsets are deterministic alternate futures, not independent dungeon seeds.
The model/controllers never receive the recipe or offset as an observation.

## Verification and scope

Before accepting variants, a neutral 100%-HP/zero-draw recipe must match the
parent's recorded fixed-pursuit trajectory for up to 32 decisions. All parents
start at full HP. Each synthetic variant is reset twice and run under the same
pursuit controller for up to 24 decisions (or death); initial observations must
differ from the original only in requested HP, and both trajectories must agree.
This is bounded replay verification, not a proof of unlimited determinism.

Only verified variants enter the six-policy, 600-decision comparison. Recovery
uses the unchanged full-health, observable-safety and 20 checked quiet-turn rule.
Known zero-decision map-parser failures may be retried once with separate workers;
all attempts are preserved. No tactical losses or divergences are retried away.

All variants retain their parent seed and family. Everything in this pilot is
labelled evaluation-only, with `training_ready=false` even when replay-verified.
The three recently reserved evaluation families stay out of training. A future
training workflow must split by parent seed, never by synthetic variant. These
are 60 related variants of six inspected encounters, not 60 independent examples
of real-game generalization.

## Run

```sh
make -C crawl-0.35/crawl-ref/source WEBTILES=y GAME=crawl-tactical-augment -j4 crawl-tactical-augment
DCSS_TACTICAL_ENGINE="$PWD/crawl-0.35/crawl-ref/source/crawl-tactical-augment" \
DCSS_TACTICAL_AUGMENT=1 \
uv run --with pexpect python .webtiles/bench/tactical/augment_encounters.py \
  .webtiles/bench/tactical/augmentation-pilot-v1.json <new-output-directory>
```

Use `--phase prepare` and then `--phase evaluate` to inspect fidelity results
before tactical evaluation. Evaluation refuses changed config, engine or source
hashes. The normal `crawl-observation-rng` and production RC are not replaced.

## Completed pilot results

All six neutral checks passed (163 recorded decisions total). All 60 variants
passed exact-initial-mutation and paired replay checks. For each family, the
four full-HP RNG variants had four distinct normalized gameplay trajectories,
not just different terminal messages. 139 Python tests and 13 Lua checks passed.

The six-controller comparison completed 360 trials and 35,041 recorded decisions:
181 recoveries, 138 observed deaths, 40 unavailable options and one unresolved
stall. One death required morgue adjudication, described below. No fitting,
controller edits or production deployment occurred.

All 181 recovered traces passed the independent recovery-boundary audit.
A live negative test also verified that the hook rejects mutation without its
opt-in environment flag and leaves the initial state unchanged.

**33/60 variants had both recovered and dead strategies; nine had no recovered
strategy; the other 18 recovered with every available strategy.** These are
controller coverage observations within the fixed budget, not proof that the
nine hard variants are unwinnable. A strategy's winning set changes across
variants, so a single original outcome is not a reliable universal label.

Recoveries out of ten variants per family:

| Family | Withdraw 0 | Withdraw 1 | Defend 0 | Defend 1 | Pursue 0 | Pursue 1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Jeremiah | unavailable | unavailable | 0 | 6 | 0 | 6 |
| Maggie | 7 | 7 | 7 | 7 | 10 | 10 |
| Eustachio | unavailable | unavailable | 8 | 8 | 8 | 8 |
| Ogre | 6 | 10 | 6 | 10 | 6 | 4 |
| Gnolls | 4 | 4 | 4 | 1 | 2 | 2 |
| Centaur | 3 | 3 | 3 | 3 | 9 | 9 |

0 means no berserk permission; 1 permits it. Ogre pursue:1 also has one stall.
Counts are not independent samples, and HP strata have different RNG offsets;
do not interpret aggregate HP rates as a controlled causal comparison. Aggregate
pursue:0 recovered 35/60 and pursue:1 39/60. This deliberately difficult synthetic
set is not comparable to the earlier fresh-case 30/30 pursuit result.

Useful examples:

- **Maggie, 100% HP:** RNG offset 1 recovered with all six strategies; offset 17
  recovered only with pursuit. Same initial observable state, different outcomes.
- **Ogre, HP-only change:** original full-HP pursue:0 recovered, but 80% HP with
  zero RNG advancement died; withdraw:1 and defend:1 recovered.
- **Eustachio, 100% HP, RNG offset 1:** defend:0 and pursue:0 recovered while their
  berserk-enabled counterparts died, reversing the original four outcomes.

For eventual training, use these outcomes to estimate strategy reliability over
alternate futures. Do not expose the RNG offset as an input or pretend the model
can identify which hidden future will occur. Keep seed/family separation and use
new real-game encounters for subsequent generalization evidence.

### Preserved failures

`ogre/variant-07`, pursue:0 (60% HP, zero RNG offset) was reported as a harness
timeout after 36 completed decisions. Its private death morgue confirms the same
character/seed died to an ogre at turn 3875 with -12/56 HP; the terminal contains
the partial redraw `die...`. The current fallback recognizes only zero-HP death
headers, not negative HP. The raw trace lacks the final terminal transition and
is not repaired or promoted to a training trajectory. A separate adjudicated
result records the death and hashes its morgue/terminal evidence. This parser
limitation remains outstanding; no source changed during the frozen comparison.

The same variant under pursue:1 stops as an unresolved stall: full 61/61 HP,
safe=true, unseen=false, no visible monsters, but a remembered invisible-monster
cell at relative (39,9) prevents the common clean-recovery check. The controller
waits instead of resolving that stale distant marker. It is not counted as a win;
the original state/trace is retained for a focused follow-up.

Artifacts are under `artifacts/augmentation-pilot-v1` (original preparation and
trials) and `artifacts/augmentation-pilot-v1-adjudicated` (explicit death
adjudication, comparison, audit). Recipes and scripts are version-controlled;
checkpoint/trace provenance is in `evidence/augmentation-pilot-v1.json`.

Use `summarize_augmentation.py <artifact-root>` for policy/family/HP comparisons
and `audit_goals.py <artifact-root> --output <audit-path>` for recovery checks.
Both operate on saved results without running or training a model.
