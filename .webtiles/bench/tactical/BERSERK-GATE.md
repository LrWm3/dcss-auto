# State-level berserk gate — 2026-09-10

The initial-context chooser was not learning the right thing. It saw one feature
vector at encounter start, although the berserk decision occurs much later. Its
cross-fit score was 60/72 on the first batch and 31/36 on the fresh second batch;
the fixed near-range policy recovered 68/72 and 36/36 respectively.

This experiment moves the decision to the actual first state where a visible enemy
is within two tiles and berserk is available. The gate chooses between:

- `near`: berserk immediately in that state;
- `never`: never berserk during the encounter.

All movement, attacks and recovery behavior remain fixed pursuit. The gate uses
HP/max HP, XL, AC, EV, enemy count/threat/distance, ranged/unique counts, berserk
availability and observable status flags. It has no seed, enemy identity, outcome
or hidden information. Training labels are paired full-recovery outcomes.

## Held-out result

The first gate, trained on the original 72 paired variants, chose `never` for 20
of 36 fresh cases and recovered 31/36. This lost five cases that near-range
berserk recovered. It was rejected.

The revised gate trained on the original 72 plus the fresh 36 paired cases (107
usable decision states; one original case had no two-tile trigger) chose `near`
for every case in a third, unseen 36-case RNG batch. It recovered 35/36, exactly
matching the near baseline. The same third batch recovered 25/36 with never.

| Third fresh batch | Recovered | Died | Budget |
| --- | ---: | ---: | ---: |
| Never | 25 | 11 | 0 |
| Near | 35 | 0 | 1 |
| Revised gate | 35 | 0 | 1 |

The gate has therefore learned a safe default, not a useful withholding rule.
The remaining budget case is a fixed recovery-horizon label, not a death.

## Interpretation

The data currently contains many examples where near-range berserk rescues the
encounter, but almost no stable, state-identifiable examples where withholding it
is better. The original batch had three near failures against never's recoveries,
but that pattern did not transfer to the second batch. Once the second batch was
included, the model correctly stopped making unsupported exceptions.

This is the desired safety behavior for a first deployment-oriented learner:
keep the strong fixed near policy until the dataset contains repeated, held-out
evidence for a specific withholding condition. The state-level gate is not exported
to the Crawl RC yet.

Evidence:

- 72 original paired variants, 36 second-batch variants and 36 third-batch paired
  variants, all with seed-preserving RNG offsets and held-out evaluation;
- third-batch gate audit: 36 episodes, 35 recoveries, one budget truncation;
- action audit passed with no harness errors or no-turn stalls;
- full suite remains 213 Python tests plus 13 Lua checks before this experiment's
  two new tests are included.

Next useful data is targeted: construct repeated encounters where near berserk
loses but contact/never wins, then test whether that condition survives a new RNG
offset. More generic fitting on the current data should remain disabled.
