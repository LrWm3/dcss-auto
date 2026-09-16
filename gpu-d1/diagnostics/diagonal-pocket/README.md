# Six enemies and a diagonal-only protected pocket

2026-09-16. Read-only follow-up to the straight hallway diagnostic, using the
same original and one-third-clumped seed-0 30M policies. User sketch interpreted
as a pocket southeast of the room's bottom-right floor tile:

```text
xxxxxxx
xgggxxx
xgggxxx
x...xxx
x.@.xxx
x...xxx
xxxx.xx
xxxxxxx
```

From the player, two southeast moves reach the pocket. It has exactly one
walkable neighbor, diagonally northwest; both cardinal corner tiles are walls.
The unchanged simulator permits movement and melee diagonally through that
corner. Native assertions check the two floor steps, cardinal blockers and
single neighbor. The retreat controls actually reach the pocket in 100% of
rollouts, verifying executable entry rather than geometry alone.

All six enemies and all 16 floor tiles are initially visible under the original
native-ray LOS rule. No hidden map information is provided to the models.
Sweep: four rotations, HP 6/12/18, weaker and tougher groups, 512 combat RNG
seeds per condition. The rosters, energy, player stats, episode tick 256/2048,
18 already-defeated enemies, policy sampling seed, and 256-action diagnostic
cap match [the six-enemy hallway test](../hallway-six/README.md). Rotation arms
share combat RNG seeds and are not independent seeds. The seen-floor scalar
is now 16/1024. Invisible disconnected padding serves terminal reset only.

Controls hold position and fight, or take the two-step diagonal route and then
hold/fight. Policy arms act freely, receive only the first route step, or receive
both route steps and then resume control. Record probability of the first
route step, arrival at the pocket, and attacks before first arrival. No training.

```sh
gpu-d1/.venv/bin/python gpu-d1/diagnostics/diagonal-pocket/run.py
gpu-d1/.venv/bin/python gpu-d1/diagnostics/diagonal-pocket/audit_training.py
```

## Results

Survival (all six enemies defeated), averaged equally over four rotations:

| Group | Player HP | Hold/fight | Retreat 2/fight | Original policy | Clump-trained policy |
|---|---:|---:|---:|---:|---:|
| Weaker | 6 | 63.7% | 98.6% | 68.9% | 87.8% |
| Weaker | 12 | 95.4% | 100% | 89.4% | 97.4% |
| Weaker | 18 | 99.9% | 100% | 97.4% | 99.8% |
| Tougher | 6 | 0.2% | 43.0% | 12.7% | 22.8% |
| Tougher | 12 | 2.0% | 82.6% | 35.0% | 56.4% |
| Tougher | 18 | 10.2% | 95.8% | 54.1% | 75.5% |

Tougher group, HP 12:

| Intervention | Original survival | Clump-trained survival |
|---|---:|---:|
| Natural policy | 35.0% | 56.4% |
| Force first diagonal step, then policy | 76.9% | 79.9% |
| Force both diagonal steps, then policy | 79.2% | 80.8% |

Natural arrival at the pocket is 53.1% original versus 78.9% clump-trained.
Arrival may be late, or the model can leave; arrival does not imply survival.
Supplying the first step alone closes much of the gap. Forced-route policy arms
remain slightly below the hold-in-pocket control: the model may leave that
position or choose different combat actions. These interventions hold starting
RNG states fixed, but actions can consume draws differently.

Directional sensitivity remains. At HP 12/tougher group:

| Route | Original survival | Clump-trained survival |
|---|---:|---:|
| Southeast, as drawn | 64.6% | 56.8% |
| Southwest | 32.2% | 45.7% |
| Northwest | 4.7% | 60.0% |
| Northeast | 38.5% | 63.1% |

Thus mixed training helps on average, not in every rotation. Both policies use
the diagonal pocket in some rollouts, but neither reliably matches a controller
that goes there immediately and stays. Different route length and map geometry
mean comparisons to the straight hallway do not isolate diagonal movement alone.

## Is the geometry novel?

Audit all 256 training floor layouts for floor tiles with exactly one walkable
8-neighbor that lies diagonally. There are 74 such pocket tiles on 45 layouts.
The motif therefore exists in the training geometry. This audit does not tell
whether either agent visited them, whether enemies created similar pressure,
or whether this exact arrangement appeared. This synthetic scenario was not
added to training; it is not evidence of an entirely unseen geometric concept.
Per-map motif counts and floor hashes are retained in the audit artifact.

Initial observation and geometry assertions passed; every rollout resolved
within 256 actions. Runtime about 13.4 seconds including compilation and map
construction. Source/checkpoint hashes, per-condition metrics and first-action
probabilities: `results/diagonal-pocket-retreat.json`. Layout audit:
`results/diagonal-pocket-training-audit.json`. Generated maps/libraries remain in
ignored `build/`; existing experiments are unchanged.
