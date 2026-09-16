import json,pathlib
ROOT=pathlib.Path(__file__).resolve().parents[2]
r=json.loads((ROOT/'results/los-model-waiting-only.json').read_text());assert len(r['results'])==4
hybrid=json.loads((ROOT/'results/los-navigation-heuristic-combat.json').read_text())
lines=['# Model plus waiting only','','Frozen 10M rest/sleep seed-0 model, same 1,024 validation episodes, 24 enemies, 15×15 wall-blocked LOS and 2,048 policy decisions. No retraining.','','Override the model action with wait if at least one currently visible enemy is awake and **no visible enemy is adjacent**. Otherwise use the model action unchanged, including attacks, target selection, movement and rest. An adjacent sleeper also prevents overriding the model. There is no retreat, heuristic attack choice, pursuit or encounter latch. Sampled model actions are drawn every decision before the override, matching baseline evaluation RNG consumption.','','## Results','','| Policy | Clears | Deaths | Timeouts | Mean physical turns | Mean forced-wait decisions |','|---|---:|---:|---:|---:|---:|']
for name,v in r['results'].items():
 m=v['metrics'];lines.append(f"| {name} | {m['clears']} ({100*m['clear_rate']:.2f}%) | {m['deaths']} | {m['timeouts']} | {m['turns']:.1f} | {m['heuristic_decisions']:.1f} |")
lines+=['','For context, previous full encounter-heuristic hybrids:','','| Policy | Clears | Deaths | Timeouts |','|---|---:|---:|---:|']
for name in ['awake-sampled','visible-sampled','awake-greedy','visible-greedy']:
 m=hybrid['results'][name]['metrics'];lines.append(f"| {name} | {m['clears']} | {m['deaths']} | {m['timeouts']} |")
lines+=['','## Paired outcomes against model alone','','| Model mode | Newly clear | Previously clear, now fails |','|---|---:|---:|']
for mode in ['sampled','greedy']:
 a=r['results']['learned-'+mode]['episodes'];b=r['results']['waiting-'+mode]['episodes']
 gain=sum(not u['clear'] and v['clear'] for u,v in zip(a,b));loss=sum(u['clear'] and not v['clear'] for u,v in zip(a,b));lines.append(f'| {mode} | {gain} | {loss} |')
lines+=['','Both learned-only controls reproduce their saved clear/death/timeout rates, kills and physical turns exactly. All evaluated actions passed the legal mask and every episode terminated. Waiting-gate checks cover distant awake enemies, adjacent enemies, sleeping-only sightings, no enemies, inactive worlds and an adjacent sleeper with a distant awake enemy. The reported forced-wait count includes decisions where the model might already have selected wait.','','These are descriptive results on a reused validation panel for one frozen model. Changes to movement, regeneration, encounter timing and combat randomness are not separately isolated. No general statistical significance or transfer claim is made.','','Reproduce:','','```sh','gpu-d1/.venv/bin/python gpu-d1/diagnostics/seek-destroy-los/run_hybrid.py --waiting-only','gpu-d1/.venv/bin/python gpu-d1/diagnostics/seek-destroy-los/report_waiting_only.py','```','','Raw: `results/los-model-waiting-only.json`.','']
(ROOT/'LOS-MODEL-WAITING-ONLY.md').write_text('\n'.join(lines))
