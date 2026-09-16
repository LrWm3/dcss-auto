# Full-map random-policy trajectory audit

`run.py` evaluates the production centered-map simulator on 1,024 episodes
(32 validation maps × 32 placements), seed 900000, 24 enemies, and a 2048
physical-turn deadline. It does not train or change the live experiment.

Run from the repository root with `gpu-d1/.venv/bin/python`:

```sh
gpu-d1/.venv/bin/python gpu-d1/diagnostics/centered-map-random/run.py --label uniform
gpu-d1/.venv/bin/python gpu-d1/diagnostics/centered-map-random/run.py --label wall-blind --mode wall_blind
gpu-d1/.venv/bin/python gpu-d1/diagnostics/centered-map-random/run.py --label untrained --checkpoint gpu-d1/learning-runs/vision15-centered-map/runs/rest-seed0/snapshots/000000000000.pt
gpu-d1/.venv/bin/python gpu-d1/diagnostics/centered-map-random/run.py --label trained-5m --checkpoint gpu-d1/learning-runs/vision15-centered-map/runs/rest-seed0/snapshots/000005013504.pt
```

Uniform chooses equally among production-valid actions. Wall-blind makes all
eight direction choices available, including wall bumps, but retains the normal
rest restriction. Checkpoint evaluations sample the actual saved policy with
AMP and fused map construction. These are separate diagnostic evaluations;
small numerical and sampling differences can change individual trajectories
from the original validation, especially the FP32 initialization evaluation.

The audit records unique tiles occupied (not tiles seen), successful moves,
maximum Chebyshev displacement from spawn, initial nearby enemies, enemies
observed awake/adjacent, attacks, damaging hits, kills, and rest opportunities.
Every reported kill must coincide with a directional attack on an adjacent enemy
with at most four HP. On nonterminal transitions, kill count changes must match
loss of living enemy observation records. Terminal observations auto-reset, so
wake/adjacency counts omit the last transition and are lower bounds; terminal
non-killing damage is also omitted. Movement includes the terminal transition
by reconstructing it from the pre-action occupancy and valid-action mask.

JSON summaries and three illustrative episode summaries go to `gpu-d1/results/`.
Compact per-decision traces stay under ignored `gpu-d1/learning-runs/` and are
not committed. Trace columns: player x, player y, action, cumulative kills,
player HP, active before step, cumulative physical turns. Discard inactive rows.

All modes share initial environments, but their combat RNG streams diverge
when actions differ. This is a mechanism audit, not a multiple-training-seed
claim about algorithm superiority.

After all four evaluations, run `plot.py` and `report.py` with the same Python
interpreter to regenerate the example figure and `CENTERED-MAP-RANDOM-AUDIT.md`.

Additional modes: `--mode heuristic` evaluates native full-map seek and destroy;
`--mode heuristic_rest` gives rest priority whenever the production mask permits
it. See `gpu-d1/CENTERED-MAP-SEEK-DESTROY.md` for results and exact commands.
