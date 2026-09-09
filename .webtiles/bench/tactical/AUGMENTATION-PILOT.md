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
