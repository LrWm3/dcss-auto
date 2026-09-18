# Middle-distance navigation remedies

Follow-up to NATIVE-CURRICULUM.md. The selected middle-band checkpoint reaches
64.06% known-stair / 68.75% exploration validation success. Test three bounded
continuations on the identical middle-distance train/validation/test fixtures.

## Prespecified comparison

All arms start with identical inherited weights from
`native-curriculum-seed0/selected.pt`. All receive 2000 additional updates,
Adam lr1e-4 with a fresh optimizer, 16 burn-in + 16 learning steps, two replay
buffers of 1024 sequences, and 16 sampled sequences per buffer per update.
Half the loss comes from pure controller demonstrations and half from the
learner buffer. Collect 32 environments per wave, cap collection at 512 steps,
and evaluate with a 1024-turn deadline. No enemies or new reward terms.

- **control**: original coarse representation; learner trajectories use 10%
  controller actions, matching the preceding curriculum's final mixture.
  Uniform sequence sampling and valid-token cross-entropy.
- **balanced**: same model; learner executes all actions, while the controller
  supplies labels. Stratify sequence sampling and equalize loss across three
  observation groups: no known stairs, known stairs inside the local crop,
  known stairs outside the local crop. Only nonempty groups are averaged.
- **exact**: same improved sampling/training, plus an exact remembered-map CNN.
  The original coarse branch stays. A zero-initialized residual output initially
  makes the additional branch contribute exactly zero to the old 96-dimensional
  global embedding. All model parameters remain trainable.

The exact input has six 70x80 binary channels: unknown, known wall, known floor
unvisited, visited floor, discovered stairs, and player. It is not the hidden
map. The local crop remains 15x15; no frontier, path or route-distance inputs
are introduced. Three convolutions (two strided) precede a flattened linear
readout. Raw observations are exact at the input; subsequent neural compression
is learned. This is not an explicit pathfinder or guaranteed topology-preserving
encoder. It increases capacity and input detail together, so the representation
comparison cannot isolate those two factors. A negative result cannot establish
that exact map information would never help with a different encoder.

Exact binary inputs are stored losslessly as bytes and converted to floats at
training time. Other prepared inputs remain float32. Buffers store no cached
learned features. AMP initial scale is 1024 for all arms; skipped overflowing
updates are recorded. Initial exact/coarse feature equivalence and binary input
semantics are checked before training. A smoke optimizer update changed inherited
weights and made the exact branch's initially zero output weights nonzero.

Seed 0 only. Reset the training RNG identically after model setup so extra
parameter initialization doesn't change initial scenario sampling. Policies
then diverge and collect different numbers of decisions. Update budget is
matched; environment decisions, wall time and parameter count are not.
Select checkpoints by mean middle-band validation success every 500 updates.
Evaluate the selected checkpoint on middle-band test and original full-size
validation/test; those test outcomes do not select checkpoints.

## Coverage audit

The prior run did not save its replay buffers. Reconstruct four collection
waves per behavior using its selected checkpoint and matched reset seeds, then
report collected and retained learning-token counts in the three groups.
Compare expert actions, 10%-teacher mixtures, and pure learner actions.
This is a new coverage measurement under that checkpoint, not a reconstruction
of the original evolving training policy's exact historical counts. Repeated
loop states count as repeated tokens, not new distinct experiences.

## Running and artifacts

Use the compiler-header CPATH from EXECUTION-OPTIMIZATION.md.

```sh
python native_remedies.py --arm exact --smoke --name native-remedy-exact-smoke-check
python native_remedies_suite.py
```

The suite runs audit, control, balanced, exact sequentially and stops on a failed
job. Checkpoints are bounded to latest and selected per arm. Maps, replay buffers
and checkpoints are not committed; JSON reports are under `results/native-remedy-*`.
The chosen test includes both known-stair navigation and exploration, so improved
attack/combat competence is outside its scope.

## Audit results

Collected valid learning tokens on matched reset batches:

| Behavior | No known stairs | Stairs in crop | Stairs outside crop | Total |
|---|---:|---:|---:|---:|
| expert | 7,569 (82.3%) | 961 (10.4%) | 667 (7.3%) | 9,197 |
| mixed | 13,416 (69.1%) | 1,000 (5.2%) | 4,998 (25.7%) | 19,414 |
| pure_learner | 16,699 (68.9%) | 1,289 (5.3%) | 6,253 (25.8%) | 24,241 |

Distant known stairs are uncommon in pure expert trajectories. Switching from
10%-teacher mixtures to pure learner trajectories adds difficult-state tokens
but barely changes their collected proportion. Equalizing category loss is a
separate intervention. The improved-training arms bundle that change with pure
learner rollouts, so this screen does not isolate those two training changes.
