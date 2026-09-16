"""Render the checked-in evaluation results without rerunning CUDA."""
import json,pathlib
HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parents[1]
data={}
for arm,mode in [('engage_now','scripted'),('heal_first','scripted'),('wait','sampled'),('rest','sampled'),('wait','greedy'),('rest','greedy')]:
    d=json.loads((ROOT/f'results/rest-recovery-{arm}-{mode}.json').read_text())
    data[arm,mode]={(r['geometry'],r['hp'],r['difficulty']):r for r in d['conditions']}
lines=['''# Sleeping-enemy recovery probes

Evaluated the existing 10,027,008-decision seed-0 wait-only and rest-to-full checkpoints, with no training or policy updates. Both use the 2048-decision deadline. The rest action is unavailable while any enemy is visible, including sleeping enemies, and at full HP. Policies have no explicit asleep/awake observation.

## Design

A 21×21 open room, player at center, one remaining required enemy, all others marked dead. Initial time is zero, and only the normal initial view is revealed. The enemy starts asleep. Native combat, regeneration, LOS, wake checks, and rest interruption are unchanged. Killing this enemy ends the episode.

- **Off-axis, wake range + 1:** enemy offset (7,1), visible and one Chebyshev tile beyond the six-tile wake radius.
- **Straight vision edge:** offset (7,0), also visible and one tile beyond wake range. These first two requests overlap in distance, so the test distinguishes their approach geometry.
- **Outside vision:** offset (8,0), hidden and rest initially legal below full HP.
- Player HP: **2/18, 9/18, 18/18**.
- Reference enemy: native kind 3, HP increased to 28, speed 10, damage 5.
- Hard enemy: native kind 4, HP increased to 48, speed 12, damage 5. These are deliberately tougher HP proxies than ordinary training enemies, not ogres.
- All eight rotations/reflections, 128 combat RNG seeds per orientation: **1,024 rollouts per table cell**. The RNG seeds repeat across orientations and conditions; these are not 1,024 independent combat seeds. No claims about variation across training seeds.
- Primary evaluation samples policy actions. Greedy evaluation is reported separately.

Controls know the enemy's location: `engage_now` walks directly toward it and keeps attacking; `heal_first` uses ordinary waits until full HP, then follows the same attack script. Learned policies receive only their normal observations, with no hidden-enemy information. Native setup assertions verify visibility, sleep, rest legality, absence of hidden monster records, zero initial decision time, and no invalid rest selections. Every rollout must terminate at the native deadline or earlier.

## Survival: sampled policies

Survival here means killing the enemy before dying. Every evaluated rollout ended in a clear or death; there were no timeouts. Each pair below is **wait-only / rest-enabled** clear percentage.

| Initial enemy position | Player HP | Reference enemy | Hard enemy |
|---|---:|---:|---:|''']
labels={'off_axis_wake_plus_one':'Visible, off-axis','straight_vision_edge':'Visible, straight edge','outside_vision':'Outside vision'}
for g,label in labels.items():
    for hp in [2,9,18]:
        cells=[]
        for difficulty in ['reference','hard']:
            cells.append(' / '.join(f"{100*data[arm,'sampled'][g,hp,difficulty]['clear']:.1f}%" for arm in ['wait','rest']))
        lines.append(f'| {label} | {hp}/18 | '+ ' | '.join(cells)+' |')
lines.append('''
## Recovery behavior

The table averages the two enemy profiles equally. Rest use means at least one macro **before the enemy wakes**, including moving out of sight and then resting. Wake HP is measured immediately after the first waking transition; it can include that turn's regeneration/damage. Full-HP starts cannot select rest by design.

| Initial enemy position | Starting HP | Rest model: rested before wake | Wait model: mean wake HP | Rest model: mean wake HP |
|---|---:|---:|---:|---:|''')
for g,label in labels.items():
    for hp in [2,9,18]:
        avg=lambda arm,k:sum(data[arm,'sampled'][g,hp,d][k] for d in ['reference','hard'])/2
        lines.append(f"| {label} | {hp}/18 | {100*avg('rest','rested_before_wake'):.1f}% | {avg('wait','wake_hp'):.1f} | {avg('rest','wake_hp'):.1f} |")
lines.append('''
Neither policy selected any ordinary waits while the enemy was asleep in the low- or half-HP sampled tests. There was one such wait per model in the full-HP visible cases across all their rollouts. This does not mean the models never heal: moving and fighting also regenerate HP.

Outside vision, the rest model's initial probability of selecting rest is **41.2% at 2 HP versus 86.9% at 9 HP**. This is the same for both enemy profiles because the enemy is hidden. By the time the monster wakes, it has rested in about 70% of low-HP episodes and 93% of half-HP episodes. It therefore responds to HP, but has not learned a consistently stronger preference for recovery as health becomes more critical.

When the enemy is already visible, the macro is masked. The rest model occasionally moves out of sight and rests (roughly 3–7% against the reference enemy, at most 1% against the harder enemy), but usually wakes it while still close to starting HP. It has not reliably learned either ordinary waiting to heal or creating a safe resting opportunity.

## Scripted controls: straight vision edge

| HP | Enemy | Engage immediately | Wait to full, then engage |
|---|---|---:|---:|''')
for hp in [2,9,18]:
    for difficulty in ['reference','hard']:
        vals=[data[a,'scripted']['straight_vision_edge',hp,difficulty]['clear'] for a in ['engage_now','heal_first']]
        lines.append(f'| {hp}/18 | {difficulty} | {vals[0]*100:.1f}% | {vals[1]*100:.1f}% |')
lines.append('''
These controls establish a real recovery opportunity: the hard enemy can kill a full-health player, but engaging while critically injured is much worse. They are not optimal combat policies. Learned policies can exceed immediate-attack survival through movement and the regeneration it permits.

## Greedy sensitivity

Greedy rest-model performance is much worse than sampled performance, even at full health. This is a separate combat/action-selection weakness and prevents treating successful resting as sufficient for a successful encounter.

| Straight visible edge | Enemy | Wait greedy | Rest greedy |
|---|---|---:|---:|''')
for hp in [2,9,18]:
    for difficulty in ['reference','hard']:
        vals=[data[a,'greedy']['straight_vision_edge',hp,difficulty]['clear'] for a in ['wait','rest']]
        lines.append(f'| {hp}/18 | {difficulty} | {vals[0]*100:.1f}% | {vals[1]*100:.1f}% |')
lines.append('''
## Interpretation and limits

The macro makes recovery behavior accessible when already legal. It has not produced a general “get healthy before a dangerous fight” policy. In particular, visible sleeping enemies still expose the missing preparation behavior. Outside-vision low-HP survival improves with the rest model, but it performs worse in several other cases. These are independently trained policies, so their survival differences do not isolate the causal effect of pressing rest; their combat strategies differ too.

This is a diagnostic suite on an artificial room with unusually durable enemies, one training seed, and fresh episode clocks. It does not replace ordinary held-out floor validation or establish generalization across trained seeds. Greedy and sampled outcomes are deliberately kept separate. Rotations/reflections share combat seeds, and native directional ties can affect trajectories.

## Reproduction

```sh
gpu-d1/.venv/bin/python gpu-d1/diagnostics/rest-recovery/run.py --reps 128 --greedy
python3 gpu-d1/diagnostics/rest-recovery/report.py
```

Checkpoints: `gpu-d1/learning-runs/vision15-rest-full/runs/{wait,rest}-seed0/snapshots/000010027008.pt`. The program rebuilds its native diagnostic library and generates its map under ignored `learning-runs/rest-recovery-probe/`. It writes six compact JSON reports under `gpu-d1/results/rest-recovery-*.json`; no new checkpoints are created. Each JSON includes per-condition behavior, survival, turns, decisions, and evaluation seconds (excluding map compilation and library build).
''')
(HERE/'README.md').write_text('\n'.join(lines))
