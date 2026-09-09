# Rich encounter inputs (v2)

The v2 adapter retains the one-choice-per-encounter goal controller, but replaces
the selector's small summary with structured player, equipment, enemy and spatial
observations. Historical V1 code, models, datasets and production RC stay intact.

## Representation

- Player: XL, absolute maximum HP, HP fraction, MP, AC/EV/SH, attributes,
  resistances, willpower, see invisible, flight, species/background and 29 skills.
- Inventory/equipment: known item subtype, equipped slot, quantity, known plus,
  brand, base damage/delay/accuracy, player-specific damage rating, armour base
  AC/encumbrance and known artefact properties. The raw snapshot retains names;
  model features exclude full item names, inventory letters and inscriptions.
  Identified wand charges are included. Duplicate equipped items have deterministic
  slots, so inventory iteration order does not change their encoding.
- Every visible hostile: type/base type, relative position, threat, reachability,
  wound category, described maximum HP, AC/EV/WL pips, resistances, known spells,
  speed description, status, ranged/reach distance and relevant flags.
- Geometry: player-known cells and anchors remain in the raw observation. The
  model receives visible terrain/cloud types and occupancy/hazard flags in a
  17x17 player-relative window, plus actual computed retreat/choke path lengths.

Monster values come from the managed `monster_info` API, not hidden live monster
HP or dungeon Lua. Described HP is approximate text; AC/EV/WL are display pips,
not exact defensive stats. Unidentified item properties remain unknown. The
observation extension executes no equipment changes, skill training or movement.

## Model encoding

`rich_features.py` produces sparse numeric features for the existing linear
outcome fitter. It includes eight nearest-enemy slots sorted by distance, x, y
and type, plus all-enemy type/spell counts, overflow count, nearby-pair and
opposing-direction counts, ranged-enemy count and HP/threat interactions.
Categorical values are explicit feature keys, not arbitrary ordinal numbers.
Numeric fields include presence indicators so missing values aren't equated with
known zero. Raw snapshots preserve all enemies, even beyond the eight slots.

This is substantially richer, but is not a neural set encoder or map reasoning
network. The local map has fixed orientation, and uncommon combinations may
require considerably more data. Item damage/delay fields are base values;
damage rating incorporates character state. The raw described monster HP is
retained but not currently parsed into a numeric model input. The model still
does not observe hidden enemies, RNG, seeds, outcomes or future events.

## Integration

Use `rich_goals.derive(parent, destination)` on an original or goal-v1 checkpoint
to create a separate rich case. It preserves the save bytes and marks replay
readiness false until separately checked. Existing HP/RNG-augmented v1 cases can
also be upgraded without applying their recipe twice.

Use `rich_goals.run(entry, case, output, option, model=...)` to collect V2 feature
rows or execute a V2 selector. `rich_goals.fit(rows)` accepts only audited
win/death rows marked as training with feature_version=2. Preserve seed splits
when building those rows; this helper is not a replacement for dataset auditing.
Rows and models carry a schema version, feature-source checksum and observation
bridge checksum; V1 models or modified definitions are rejected. The old `run_goals` entry point intentionally
continues to mean V1.

Old labels have no rich initial snapshots and must not be silently treated as
V2 training data. Collect verified rich snapshots and fresh policy labels before
the next substantive retraining. Actual gear/skill/XL/attribute/resistance
mutation recipes are now available through the separate lab-only
[character collection](CHARACTER-DATASET.md), not through this observation adapter.

## Verification

`test_rich_features.py` checks distinguishability for gear, skills, XL, AC, enemy
identity, spells, wounds, arrangement and visible clouds. Nonvisible cells are
excluded from local map encoding; navigation summaries still use player-known
remembered terrain. Seed/RNG metadata do not alter the vector. Tests check entity-order invariance and reject
old schemas and held-out training rows.

`check_rich_goals.py OUTPUT` runs a live pilot on three original encounter families:
orc priest, Jeremiah, and a held-out ribbon-worm encounter. For each it compares
12 ordinary-controller actions on the original observation versus two rich
resets, then collects all six strategy trials. Its small 20-epoch fitted model
is an integration smoke test, not a replacement model or performance claim.

Run with the augmentation lab engine and `DCSS_TACTICAL_AUGMENT=1`, as the pilot
uses existing recipe-backed variants. Originals and production are untouched.

Completed final pilot: `artifacts/rich-goals-v2-pilot-v2`. All three 12-action
prefix checks passed against the original and repeated rich observations.
All 18 fresh policy outcomes matched the original matrix: 14 recoveries, two
deaths, two unavailable choices; all audited. Snapshots contain 1,156, 2,004 and
1,787 sparse feature entries respectively. 173 Python tests and 13 Lua checks pass.
Evidence: [evidence/rich-goals-v2-pilot-v2.json](evidence/rich-goals-v2-pilot-v2.json).
