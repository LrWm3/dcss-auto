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

## Completed training screen

All three arms finished 2000 updates without AMP overflow skips. Checkpoint
selection used only middle-band validation. Neither proposed remedy produced a
convincing overall improvement over the starting checkpoint.

| Model | Selected update | Middle test known / explore | Original full-size test known / explore |
|---|---:|---:|---:|
| Starting curriculum checkpoint | — | 64.84% / 69.53% | 31.25% / 56.25% |
| Continued control | 1000 | 61.72% / 74.22% | 27.34% / 54.69% |
| Pure learner + balanced coverage | 500 | 62.50% / 69.53% | 35.16% / 50.78% |
| Balanced + exact-map residual | 500 | 67.97% / 64.84% | 27.34% / 43.75% |

Both test sets have 128 scenarios per condition, grouped on 32 held-out maps.
This is one training seed; a few percentage points should not be interpreted as
an established improvement. The mean middle-band test score barely changes
across arms, and exact-map transfer to longer routes is worse. On original
full-size validation, known/explore success is 29.69%/48.44% for control,
31.25%/50.00% for balanced, and 34.38%/37.50% for exact. Thus no arm establishes
reliable native-map navigation across these evaluation groups.

Selected middle-band validation known/explore scores are 64.06%/67.19% for
control, 67.19%/70.31% for balanced, and 64.06%/60.94% for exact, versus
64.06%/68.75% initially. Later training did not consistently improve them.
Exact reaches 68.75% known-stair validation at update 2000, but exploration
falls to 53.12%; it is not the selected checkpoint.

| Arm | Training + collection, excluding evaluation | Collected decisions | Replayed supervised targets | Parameters |
|---|---:|---:|---:|---:|
| Control | 191.51s | 101,673 | 954,709 | 229,476 |
| Balanced | 188.49s | 124,008 | 928,983 | 229,476 |
| Exact | 212.97s | 138,541 | 935,843 | 786,460 |

These are imitation/DAgger updates, not PPO. Speed is not directly comparable
to PPO decisions/s, and evaluation/initial compilation add wall time. All maps
are native 80x70. Exact inputs increased observed GPU usage to about 6.1 GB.

The audit identifies sparse distant-stair expert coverage, but balancing it
has not fixed the behavior. The exact-map screen tests one small encoder and
training budget; it does not establish that exact spatial information is
unhelpful. Raw detail, learned routing, and adequate training are different
requirements. Keep the original curriculum checkpoint as the reference rather
than promoting any of these continuations.

## Exact-branch reliance check

`native_remedy_exact_ablation.py` zeroes the selected exact model's residual
readout, retaining its other trained weights. This is an out-of-distribution
intervention, not a separately trained capacity control.

| Evaluation | Normal known / explore | Exact residual zeroed |
|---|---:|---:|
| Middle validation | 64.06% / 60.94% | 68.75% / 64.06% |
| Original full-size test | 27.34% / 43.75% | 29.69% / 50.00% |

There is no aggregate benefit from the learned residual in these evaluations;
removing it improves both categories. This does not establish that all spatial
encoders would fail, or that the branch never helps individual cases.

## Recurrent replay diagnostic

`native_replay_audit.py` follows two batches of 32 greedy middle-band training
trajectories per checkpoint. At intervals after 64 steps it holds observations
and weights fixed, comparing live recurrent execution to replay initialized at
zero with a limited history. It also replays the full prefix as a numerical
control. Sampling active states late in an episode overrepresents difficult
and looping trajectories; these fractions are not estimates over all episodes.

The 16-step history matches the history available at the first learning token
of our training chunks. Later learning tokens have up to 31 preceding steps;
the diagnostic also checks 31 and 64. These are replay probes, not new training
runs with longer memory. Full-prefix replay uses the same encoded observations
and avoids changes in encoder outputs as a confound.

| Checkpoint | Sampled active states | Action disagreement: 16 prior steps | 31 prior steps | 64 prior steps | Full prefix |
|---|---:|---:|---:|---:|---:|
| Starting checkpoint | 480 | 36.25% | 32.50% | 28.54% | 0.00% |
| Balanced selected | 497 | 33.00% | 26.76% | 22.33% | 0.00% |
| Exact selected | 550 | 31.45% | 26.73% | 16.00% | 0.18% |

Mean KL(live || replay) for the 16-step history is respectively 0.343,
0.295, and 0.173 nats. Full-prefix KL is about 1e-7 nats for all three;
the one full-prefix argmax discrepancy is consistent with numerical sensitivity
near an action tie. Fused-vs-cell numerical differences therefore do not explain
the large truncated-history differences.

This establishes an internal-state mismatch on these sampled trajectories.
It does not yet establish how much rollout failure the mismatch causes. The
teacher negative log likelihood is not uniformly better under full-history
replay either: limited-history training and live evaluation solve different
conditional prediction problems. A lower truncated-replay training loss alone
is consequently not a reliable indicator of improving live behavior.

The next controlled change should reconstruct the recurrent state from the
full episode prefix under current weights (without gradient), then train on
the same short learning chunk. This preserves bounded backpropagation while
matching the actual history. Compare against the current truncated replay on
the same fixtures and starting checkpoint before changing representation again.
Increasing burn-in only to 64 is unlikely to eliminate the measured mismatch.
That training comparison has not been run in this screen.

All three training runs and both diagnostic evaluations are complete. No PPO
continuation was launched from these results.
