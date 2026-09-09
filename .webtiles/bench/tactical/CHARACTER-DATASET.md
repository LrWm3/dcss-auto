# V2 character augmentation

`character_dataset.py CONFIG OUTPUT` collects fresh rich-V2 observations and
strategy outcomes on disposable checkpoint copies. It never fits or deploys a
model. All six goal/berserk combinations are replayed on each accepted variant.
Original saves, V1 datasets, models and the production RC are left unchanged.

## Initial recipe grid

`character-training-v1.json` selects one encounter from each of the twelve
existing training seeds, favoring high initial summed monster threat. It requests
19 profiles per encounter (228 total, including controls):

| Axis | Profiles |
| --- | --- |
| Control | Original character, full HP |
| Skills | Axes -3/+3, Fighting +3, Dodging +3 |
| Level | XL -2/+2 |
| Attributes | Strength -4/+4, dexterity +4, intelligence +4 |
| Gear | +0 hand axe, +3 war axe, +2 robe, +0 plate armour |
| Resistances | Add one innate level of fire, cold, poison or electricity resistance |

These change actual engine state, not feature vectors. One axis changes at a
time. HP is normalized to the resulting maximum for every profile, including
the control; the gameplay RNG offset is zero. Derived HP, MP, damage, defenses
and threat ratings may change legitimately with a profile. This is not yet a
cross-product of character profiles with HP and RNG offsets.

The limited gear presets replace an existing equipped, uncursed, non-artefact
item with plain identified equipment. They do not append inventory duplicates.
Resistances use Crawl's permanent mutation machinery; capped/unavailable
resistances are excluded. XL uses the engine's wizard level setter without
normal attribute increases or skill training. Thus these are synthetic character
profiles, not claims about naturally leveled builds. Only living, untransformed,
non-berserk Minotaurs are supported initially.

## Lab engine

Apply `engine-patches/tactical-character.patch` after the existing
`tactical-augmentation.patch` and observation RNG patches. Build a separate binary:

```sh
make -C crawl-0.35/crawl-ref/source WEBTILES=y GAME=crawl-tactical-character -j4 crawl-tactical-character
```

The new managed-Lua binding is `you.tactical_character(axis, name, value)`.
It requires `DCSS_TACTICAL_CHARACTER=1`. The dataset runner additionally requires
the HP augmentation opt-in and the explicitly named character lab engine:

```sh
DCSS_TACTICAL_ENGINE="$PWD/crawl-0.35/crawl-ref/source/crawl-tactical-character" \
DCSS_TACTICAL_CHARACTER=1 DCSS_TACTICAL_AUGMENT=1 \
uv run --with pexpect python .webtiles/bench/tactical/character_dataset.py \
  .webtiles/bench/tactical/character-training-v1.json \
  .webtiles/bench/tactical/artifacts/character-training-v1
```

Use a new output directory for each run; completed evidence is never overwritten.
`character-pilot-v1.json` runs all profiles on one encounter with
`verification_only: true`, without collecting full policy labels.

## Acceptance and outputs

For every parent, the new engine must reproduce the old engine's unmodified
initial observation and twelve-action prefix. Every variant must reproduce its
own twelve-action prefix on two independent resets. Mutation setup uses an
explicitly seeded local RNG, and checks that the gameplay draw count is unchanged.
The harness checks the requested stat change, resulting full HP, unchanged turn,
position, floor, visible enemy locations/wounds, and known terrain/clouds.
No-op or unsupported profiles are recorded but excluded, not called defeats.

Full trials retain raw rich observations and V2 feature rows. Success and death
labels are re-audited from transition evidence using the existing shared recovery
criterion. Unavailable options remain masked. Timeouts and stalls are unknown,
not deaths; an incomplete strategy matrix is excluded from training.

- `manifest.json`: pinned inputs, source hashes, engines and selected parents.
- Per-family `progress.json` / `family.json`: verification evidence and results.
- `coverage.json`, `results.json`, `labels.json`, `summary.json`: collection audit.
- `training-rows.json`: terminal rows from complete, verified training variants,
  including all-win and all-loss cases.
- `mixed-training-rows.json`: subset where at least one available strategy wins
  and at least one dies, for focused strategy discrimination.

All derivatives retain the parent's seed split. No validation, test or reserved
evaluation seeds are collected into this training batch. The variants are
correlated augmentations of twelve existing seeds, not 228 independent seeds.
Keep all linked traces and immutable checkpoint copies with the exported rows.

Before fitting, call `character_audit.load(collection)` (or `mixed=True`) rather
than trusting exported JSON alone. It rechecks source/input hashes, parent and
variant bytes, paired traces, feature vectors, option masks, trial provenance,
seed splits and terminal labels. Its CLI writes a checksum-pinned
`training-index.json`; run it with the same Python/pexpect environment.

The first interrupted pilot is retained under `artifacts/character-pilot-v1`.
Its skill setup was correctly rejected by the RNG guard: the one-argument local
RNG constructor draws its sequence from the gameplay stream. The corrected
two-argument constructor supplies both values without consuming gameplay RNG.

The corrected verification-only pilot at `artifacts/character-pilot-v2` accepted
18 of 19 profiles. The +0 plate-armour profile was correctly rejected because it
duplicated the control's equipment and features. All five requested mutation axes
passed paired replay and stat checks. Examples: Fighting +3 raised maximum HP
47→52; XL 5→3/7 changed it to 34/60; replacing plate with a +2 robe changed
AC/EV 14/6→7/11. All four resistance profiles changed their observed resistance
0→1. The independent audit and 179 Python / 13 Lua tests passed. This pilot
contains no policy training rows; full labels are collected separately.
Evidence: `evidence/character-pilot-v2.json`.
