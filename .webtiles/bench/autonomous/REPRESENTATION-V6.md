# Spatial and entity representation (V6)

V6 replaces hashed inputs with explicit geometry, properties, and bounded text.
The historical V5 entry point and weights remain compatible with existing runs.
V6 requires a fresh bootstrap: its weights cannot meaningfully reuse V5 columns.

## Inputs and model

- Player-relative 17×17 grid: known/visible/mapped/passable/frontier/excluded/
  unsafe/occupied cells, terrain classes, cloud classes, and unknown-type flags.
- Every monster in that window occupies its own tile. No nearest-eight cutoff
  or distance-sort reordering. Each record includes properties, presence masks,
  status, spell-effect flags, and bounded name/spell/speed text.
- All 52 inventory slots contain separate item records. A shared item encoder
  pools them with presence masks; actions bind directly to their item/target.
  Pickup actions bind to the matching player-visible floor item.
- Player resources, resistances, individual skills, branch/level values,
  species/background/god, equipment and status information. Ordinary Lua now
  exports piety rank, haste/slow/exhaustion and other available status flags.
- Four recent actions: HP and turn changes, rejected dispatches, and last-seen
  enemy positions. History survives snapshots and is included in replay.
- A convolutional map encoder, shared item encoder and player encoder feed an
  action-conditioned scorer. Policy and critic have independent parameters.
  The spatial tensor is stored/encoded once for the legal-action list. V6's
  training feature cache is limited to 128 states.

Names use bounded UTF-8 bytes and explicit truncation bits, not hash buckets.
Item effect flags use identified player-visible names; unidentified subtype
fields cannot reveal hidden potion/scroll identities.

## Correctness fixes

The replacement encodes actual branch/level values, reserves a distinct unknown
action type, and never associates an untargeted action with an enemy at (0,0).
Cell collections accept both Lua array and map encodings. Unknown properties
have presence masks instead of being silently equated with known zero values.
Missing absolute player positions are no longer fabricated as (0,0). Where
ordinary Lua does not expose them, remembered terrain verifies displacement;
ambiguous movement discards historical enemy positions instead of guessing.

## Launch and resume

From the repository root, use a new run directory:

```sh
.webtiles/bench/tactical/.rl-venv/bin/python \
  .webtiles/bench/autonomous/train_structured_agent.py \
  --run-dir .webtiles/bench/autonomous/artifacts/foundation-general-training-v6 \
  --cycles 1
```

Use the same entry point and run directory to resume. For the time scheduler,
prefix its usual command with `DCSS_REPRESENTATION=spatial-v6`; child processes
inherit the representation. Cross-version checkpoint loading fails explicitly.
Evaluation identities include all V6 encoder/model/history/bridge files.

## Validation and limits

`test_structured_representation.py` checks local spatial changes, the ninth
monster, monster-order invariance, item effects, missingness, hidden subtype
protection, action-target binding, movement history and encoder gradients.
`smoke_structured_agent.py --output NEW_DIRECTORY` exercises real Crawl
collection, exact snapshot/RNG replay, behavioral cloning, critic and actor
updates, model reload, and a learned-policy actor. The actor's KL guard may
reject an update; the smoke report records that rather than claiming learning.

The model is not yet proven stronger. Geometry outside the local window still
uses navigation distances and summary counts. Text fields are bounded, history
is four decisions rather than recurrent memory, and exact hidden status timers
are not exposed by ordinary Lua. Missing values remain explicitly unavailable.
Legacy replay can supply spatial/item inputs but lacks the new history/status
fields; fresh collection supplies them. No long training run is launched by
the smoke test.

Validated locally on 2026-09-11:

- `artifacts/representation-v6-smoke-02/result.json`: 64 teacher transitions,
  exact feature/history and RNG replay, model reload equality, learned actor
  completing 16 decisions. About 1.05 ms forward / 13.3 ms including encoding
  on the tested observation; 1,090,946 policy-plus-critic parameters.
- `artifacts/representation-v6-cycle-smoke/latest_status.json`: one complete
  bounded collection/train/counterfactual/evaluation cycle, zero failures,
  three accepted policy update steps. This tiny smoke uses 16-decision games;
  it is a plumbing test, not evidence of gameplay improvement.
