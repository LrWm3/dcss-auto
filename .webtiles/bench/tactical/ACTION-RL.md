# Per-action RL pilot — 2026-09-10

The environment and training loop work; the learned pilot does **not** beat
scripted pursuit. No production controller, RC, or model was replaced.

## Measured result

Run: `artifacts/action-ppo-v3`, using `artifacts/action-pilot-v2/config.json`.
Six independent workers completed 6,144 PPO training actions in 119.39 seconds
(51.46 aggregate actions/s including model setup/fitting; rollout progress was
about 53/s). Validation runs afterward and is excluded from this timing.
This is not directly comparable to the earlier fixed-trace simulation benchmark.

| Policy | Recovered | Died | Budget exhausted |
| --- | ---: | ---: | ---: |
| Random legal actions | 3 | 3 | 2 |
| Pursuit, no berserk | 8 | 0 | 0 |
| Pursuit, adjacent-enemy berserk | 8 | 0 | 0 |
| Learned PPO, deterministic masked actions | 3 | 4 | 1 |
| Historical pursuit (broader action set) | 8 | 0 | 0 |

Each policy faced the same eight validation variants, with a 192-request limit.
These are **four encounter families from one validation seed, two RNG offsets
each**, not eight independent seeds or a pristine final test. Historical pursuit
retains its macros and emergency tools, so report it separately; the first two
pursuit policies use exactly the learner's action set.

Training completed 46 episodes: 5 recovered, 18 died, 23 exhausted the budget.
Six partially completed episodes were closed when the fixed training budget ended;
these are administrative closes, not deaths or successful recoveries.
The final run had no harness errors or no-turn stalls. All 84 new-adapter episode
records passed the transition/mask/reward/recovery/evidence auditor. The eight
historical-controller results were independently checked against their event logs
and all reached 20 clean turns. 195 Python tests and 13 embedded Lua checks passed.

The validation action histograms show strong northeast/southwest oscillation in
several cases and prolonged waiting in both ribbon-worm variants. No validation
episode used berserk. This small fit has not learned dependable basic combat;
it provides no evidence of an advantage over either random play or pursuit.

## Interface

- Ten choices: eight direction moves/bump attacks, single-turn wait, berserk.
  No hidden Tab, scripted combat, automatic rest, item use, or stair action.
- Mask known unsafe/withheld/excluded/untraversable cells and attacks on known
  allies; mask unavailable berserk. This is a conservative prompt-free action
  subset, not every legal Crawl action. Autopickup is disabled in derived cases.
- Observe the existing rich V2 state features: player/gear/skills, monster slots,
  geometry, clouds, etc. Encode with 8,192 stable signed feature-hash bins and
  stack four frames, including previous action, HP change and recovery counter.
  Hash collisions, finite enemy slots and short memory remain limitations.
  Seed, RNG offset and outcome labels are not model inputs.
- Success means full HP, no observable threat or harmful status, and 20
  consecutive clean single-turn transitions on the same floor. Clean movement
  also counts; it does not force 20 waits or prove no enemy exists outside sight.
- Reward: +10 recovery, -10 death, -.01/request, potential-based HP shaping
  with gamma .995 and scale .2; rejected zero-turn actions get an extra -.05.
  No reward for enemies merely disappearing from view.
- Budget exhaustion and eight consecutive rejected actions truncate episodes;
  they are not deaths. Harness failures abort instead of generating gameplay
  labels. Nonterminal commands consuming more than one turn fail for inspection.
  Forced incapacitation and broader actions still need explicit future support.

`action_env.py` provides the Gym environment and action-matched baselines;
`prepare_action_pilot.py` derives and verifies cases; `train_action_ppo.py` fits
and evaluates; `audit_action_episodes.py` checks compact transition evidence.
Raw observations, flushed pre-action requests, action audits, morgues, source
snapshots, checksums and the learned model are retained in the artifact directory.

## Data and fitting

Training: six audited control encounter families from seeds 83019001, 83018001,
83017001, 83017002, 83019003, 83018005, with RNG offsets 0/1/2 (18 cases).
Validation: seed 83017003, encounters 008/013/023/018, offsets 0/1 (8 cases).
Seed 83017004/test was not loaded. No validation labels were fitted or used for
checkpoint selection. Existing validation has been studied previously.
All 26 variants replayed twice in preflight: 826 actions, matching initial states
and repeated trajectories, no zero-turn requests. Only newly derived cases changed.

[MaskablePPO](https://sb3-contrib.readthedocs.io/en/master/modules/ppo_mask.html)
uses masks inside each subprocess and during prediction. CPU, seed 42, six workers,
128 rollout steps/worker, batch 128, four epochs, learning rate .0003,
gamma .995, entropy coefficient .01, separate actor/critic layers [128,128].
This is eight updates from random initialization, not a converged training run.

## Reproduce locally

Requires the verified `crawl-tactical-sim` binary, existing parent encounter
artifacts, split manifest, and `artifacts/simulation-cache-v1` from the simulation
benchmark. This is not a standalone downloadable dataset.

```sh
uv venv --python 3.11 .webtiles/bench/tactical/.rl-venv
uv pip install --python .webtiles/bench/tactical/.rl-venv/bin/python torch==2.14.0+cpu --index-url https://download.pytorch.org/whl/cpu
uv pip install --python .webtiles/bench/tactical/.rl-venv/bin/python sb3-contrib==2.9.0 stable-baselines3==2.9.0 gymnasium==1.3.0 numpy==2.4.6 pexpect==4.9.0 lupa==2.8
.webtiles/bench/tactical/.rl-venv/bin/python .webtiles/bench/tactical/prepare_action_pilot.py --output /absolute/new/cases
.webtiles/bench/tactical/.rl-venv/bin/python .webtiles/bench/tactical/train_action_ppo.py --config /absolute/new/cases/config.json --output /absolute/new/run --steps 6144
.webtiles/bench/tactical/.rl-venv/bin/python .webtiles/bench/tactical/audit_action_episodes.py /absolute/new/run
.webtiles/bench/tactical/.rl-venv/bin/python -m unittest discover -s .webtiles/bench/tactical -p 'test_*.py'
```

Outputs must be new directories. PPO rounds requested steps up to full rollouts
of 768; the training result records the actual count.

## Failures caught before the completed run

`action-ppo-v1` aborted because the old parser did not recognize a genuine death
with drained HP (`-2/56 (61) HPs`). A parser override in the new adapter handles
that syntax and has a regression test. Worker-crash cleanup is now bounded.
`action-ppo-v2` aborted because automatic scroll pickup added a second turn to a
movement request. New `action-pilot-v2` RCs disable autopickup globally and at each
ready callback. Both failed runs retain evidence and failure notes; neither
produced a usable model. Existing frozen adapters and cases were not modified.

## Next experiment

Use **training-only pursuit demonstrations** to initialize action prediction,
verify it imitates basic combat on training cases, then compare that initialization
against RL fine-tuning under a fixed budget. Keep validation out of fitting and
reserve test for a later fixed comparison. This should make early training more
informative than random walking; it is a proposal, not a demonstrated improvement.
Broaden actions and difficult encounters after basic action competence is reliable.
