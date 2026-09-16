# Wall and retreat diagnostics

Run `gpu-d1/.venv/bin/python gpu-d1/diagnostics/deaths/run_walls.py` from the
repository root. Reevaluate the three 10M reward policies on the original 1,024
validation episodes, at 2048 turns, without training or changing observations.
Existing diagnostics and result files are preserved. New output is
`gpu-d1/results/vision15-wall-retreat-diagnostics.json` (compact JSON to stay
under the repository's per-file size limit).

The new extension includes unchanged simulator dynamics. It records:

- Non-floor neighbors among the eight movement directions, with out-of-bounds
  positions counted separately. Known walls and unknown neighbors are separate
  fields. A wall can constrain escape or protect against enemy approaches.
- Empty walkable neighboring tiles and moves reducing enemy adjacency before
  enemies respond, as in the earlier diagnostics.
- Moves with an empty walkable onward neighbor, excluding the player's starting
  tile; also the subset reducing adjacency. This is a two-step local geometry
  check, not a global escape-route search.
- Whether the chosen move reduces adjacency or enters a tile with no onward
  empty neighbor except backtracking. Enemy occupancy is frozen for this check,
  so such a position is not necessarily a permanent terrain dead end.

Per death, preserve fatal geometry, snapshots 5/10/20/50 turns earlier when
available, and the first low-HP state within the final 50 turns. The final 20-
and 50-turn windows summarize walls, available exits, boxed-in turns, loss of
all empty exits, moves into local dead ends and low-health opportunities to
reduce adjacency versus actual moves taken. Low health is <=4 of 18 HP.

Actual simulator geometry is used for analysis, including onward squares that
may not yet be known to the player. Known walls and unknown adjacent squares
are included to expose this distinction. No hidden information is fed to the
policy. No immediate or onward option should be described as a guaranteed safe
escape: pursuing enemies, timing and longer-range topology are not modeled by
these geometry counts. Conditioning on deaths also changes the mix of states
when comparing stronger and weaker policies.

Checks cover open terrain, a corridor, a corridor end, a one-cell spur,
enemy-blocked exits and unknown walls. Every active evaluated turn must satisfy
walls + boundary positions + adjacent enemies + empty moves = 8, and onward
options reducing adjacency cannot exceed all options reducing adjacency.
Full simulator state/observation/mask parity is checked for 128 steps per policy;
all final outcome/kill/turn metrics must match prior evaluations exactly.
Original fatal-action replays must still reproduce death. Source hashes and
checkpoint hashes are recorded. Traces (~192 MiB per policy) remain in memory
and are discarded; compiled libraries and logs use existing ignore rules.

## Results (2026-09-15)

All original outcome metrics reproduce exactly. All geometry and parity checks
passed. Percentages below concern fatal episodes, not all episodes.

| Measure | Baseline | Death -4 | Completion-focused |
|---|---:|---:|---:|
| Mean walls before fatal turn | 2.90 | 3.39 | 3.53 |
| No empty neighboring tile before fatal turn | 11.5% | 16.5% | 23.8% |
| Move reducing adjacency with an onward step at fatal turn | 80.9% | 76.8% | 64.4% |
| Used a reducing-adjacency move when available at low HP, last 50 turns | 28.1% | 33.9% | 44.1% |
| Ever boxed in during last 50 turns | 22.2% | 35.2% | 42.7% |
| Moved into a local dead end during last 50 turns | 6.0% | 12.1% | 27.9% |

Most deaths do not occur with every adjacent movement tile blocked. Most also
have a move that reduces immediate crowding and permits an onward step. This
weakens “there was literally nowhere to move” as the general explanation, but
not the possibility that available moves merely delay death.

The stronger death-penalty policy takes a greater fraction of available
crowding-reducing moves at low HP in these fatal windows. Its remaining deaths
are more wall-constrained; this may reflect which episodes still fail, rather
than worse positioning overall. Geometry alone cannot establish whether walls
are helping or harming survival. Longer alternative rollouts would be needed
to test meaningful escape rather than immediate movement opportunity.
