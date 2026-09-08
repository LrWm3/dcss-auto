"""Discover encounter trajectories, capture checkpoints, and quarantine divergence.

Private games only. Baseline is a controller macro-decision, not one turn.
The discovery trace is the reference: verification never replaces it with a
more convenient replay. All cases from a seed share one dataset split group.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import shutil

from bench import Environment, ENGINE, ROOT, HERE, sha
from collect_cases import compare
from experiment import recovered
from index_cases import build
from verify_resume import normalized
from dataset_splits import MANIFEST, partition_map

TRIGGER = {'monster': '*', 'floor': 'D:1'}


def write(path, obj):
    path.write_text(json.dumps(obj, indent=2) + '\n')


def enemies(state):
    return list(state.get('monsters', {}).values())


def encounter_recovered(state):
    # Passive flight/parry can last an entire floor. They must not merge every
    # otherwise recovered fight into one episode. Unknown statuses still block.
    if any(state.get(k) for k in ('berserk','cooldown','confused')):
        return False
    state = dict(state)
    statuses = state.get('status', '').split(',')
    state['status'] = ','.join(s for s in statuses
        if re.sub(r'\s*\(expiring\)$', '', s.strip()) not in ('flying','parry'))
    return recovered(state)


def endpoint(state, initial_floor):
    if state.get('terminal') == 'death': return 'death'
    if state.get('floor') != initial_floor: return 'floor_change'
    if encounter_recovered(state): return 'safe_recovery'
    return 'verification_budget'


class Segmenter:
    """Keep LOS breaks, poison and recovery in the same encounter.

    End only at full-health observable safety, floor change, death or budget.
    A floor change is labelled separately, never called a victory.
    """
    def __init__(self, seed):
        self.seed = seed
        self.active = None
        self.cases = []

    def observe(self, state, decision):
        if (self.active and not state.get('terminal')
                and state['floor'] != self.active['floor']):
            self.finish(decision, 'floor_change')
        if self.active is None and enemies(state):
            self.active = dict(seed=self.seed, start=decision, floor=state['floor'],
                start_turn=state['turn'], start_hp_fraction=state['hp']/state['max_hp'],
                min_hp_fraction=state['hp']/state['max_hp'], enemies=[], max_threat=0)
        if self.active is None:
            return
        a = self.active
        for enemy in enemies(state):
            if enemy['name'] not in a['enemies']:
                a['enemies'].append(enemy['name'])
            a['max_threat'] = max(a['max_threat'], enemy['threat'])
        if not state.get('terminal'):
            a['min_hp_fraction'] = min(a['min_hp_fraction'], state['hp']/state['max_hp'])
        if state.get('terminal'):
            self.finish(decision, 'death')
        elif encounter_recovered(state):
            self.finish(decision, 'safe_recovery')

    def finish(self, decision, outcome):
        if self.active is None:
            return
        a = self.active
        a.update(end=decision, decisions=decision-a['start'], outcome=outcome)
        a['hp_fraction_loss'] = a['start_hp_fraction']-a['min_hp_fraction']
        a['reasons'] = []
        if outcome == 'death': a['reasons'].append('death')
        if a['hp_fraction_loss'] >= .4: a['reasons'].append('large_hp_loss')
        if a['max_threat'] >= 3: a['reasons'].append('red_threat')
        if a['decisions'] >= 100: a['reasons'].append('long_encounter')
        if not a['reasons']: a['reasons'].append('comparison_success' if outcome == 'safe_recovery' else outcome)
        # A no-action boundary is not an encounter example.
        if a['decisions'] > 0:
            self.cases.append(a)
        self.active = None


def discover(root, source, seed, cfg):
    work = root / ('seed-' + seed)
    env = Environment(work, source_rc=source, seed=seed, capture_config=TRIGGER)
    segments = Segmenter(seed)
    result = dict(seed=seed, outcome='decision_budget', candidates=[])
    noops = 0
    try:
        state = env.launch()
        if state.get('terminal'):
            raise RuntimeError('Death before discovery start')
        segments.observe(state, 0)
        for decision in range(1, cfg['max_decisions']+1):
            before = state
            state = env.step('baseline')
            segments.observe(state, decision)
            if state.get('terminal'):
                result['outcome'] = 'death'; break
            noops = noops+1 if state['turn'] == before['turn'] else 0
            if noops >= 12:
                result['outcome'] = 'no_turn_stall'; break
            if len(segments.cases) >= cfg['encounters_per_seed']:
                result['outcome'] = 'encounter_budget'; break
        segments.finish(decision, result['outcome'])
        result['decisions'] = decision
    except Exception as exc:
        result.update(outcome='harness_error', error=str(exc))
    finally:
        env.close()
    trace = env.work/'transitions.jsonl'
    result.update(worker=str(env.work), trace=str(trace), candidates=segments.cases)
    if trace.exists(): result['trace_sha256'] = sha(trace)
    write(work/'discovery.json', result)
    print(json.dumps({'discovery':seed, 'outcome':result['outcome'], 'candidates':len(segments.cases)}), flush=True)
    return result


def select(discoveries, target):
    """Round-robin seeds, prioritizing difficult cases within each seed."""
    groups = []
    for discovery in discoveries:
        rows = [dict(r, discovery_trace=discovery['trace'],
                     discovery_sha256=discovery['trace_sha256'])
                for r in discovery['candidates']
                if r['outcome'] in ('death', 'safe_recovery', 'floor_change')]
        rows.sort(key=lambda r: (r['outcome']=='death', r['hp_fraction_loss'],
                                r['max_threat'], r['decisions']), reverse=True)
        groups.append(rows)
    selected = []
    while any(groups) and len(selected) < target:
        for rows in groups:
            if rows and len(selected) < target:
                selected.append(rows.pop(0))
    for i, row in enumerate(selected): row['id'] = f'encounter-{i+1:03d}'
    return selected


def capture(root, source, row):
    work = root/row['id']; work.mkdir()
    case = work/'case'
    result = dict(id=row['id'], seed=row['seed'], case=str(case), candidate=row,
                  trials=[], training_ready=False)
    env = Environment(work, source_rc=source, seed=row['seed'], capture_config=TRIGGER)
    try:
        trace = Path(row['discovery_trace'])
        if sha(trace) != row['discovery_sha256']: raise ValueError('Discovery trace mutated')
        rows = [json.loads(line) for line in trace.read_text().splitlines()]
        reference = [rows[row['start']]['observation']] + [
            r['next_observation'] for r in rows[row['start']:row['end']]]
        state = env.launch()
        # Check EVERY prefix boundary, not just HP/floor at the chosen contact.
        for i in range(row['start']+1):
            if normalized(state) != normalized(rows[i]['observation']):
                raise ValueError(f'Discovery prefix divergence at decision {i}')
            if i < row['start']: state = env.step(rows[i]['action'])
        result['prefix_fidelity'] = dict(passed=True, boundaries=row['start']+1)
        meta = env.save_checkpoint(case, row['start'])
        result['initial'] = {k:v for k,v in state.items() if k in ('floor','turn','hp','max_hp','monsters','status')}
        trajectories = []
        for mode in ('reset','reset_repeat'):
            state = env.reset(case)
            states = [state]
            for recorded in rows[row['start']:row['end']]:
                if state.get('terminal'): break
                state = env.step(recorded['action']); states.append(state)
            trajectories.append(states)
            result['trials'].append(dict(mode=mode, outcome=endpoint(state, reference[0]['floor']),
                decisions=len(states)-1, worker=str(env.work),
                transitions_sha256=sha(env.work/'transitions.jsonl'),
                discovery_fidelity=compare(states, reference)))
            env.close()
        result['repeatability'] = compare(*trajectories)
        result['uninterrupted_fidelity'] = compare(trajectories[0], reference)
        result['training_ready'] = result['repeatability']['passed'] and all(
            t['discovery_fidelity']['passed'] for t in result['trials'])
        meta.update(training_ready=result['training_ready'], fidelity=result['uninterrupted_fidelity'],
                    repeatability=result['repeatability'], discovery=row)
        write(case/'case.json', meta)
    except Exception as exc:
        result.update(error=str(exc), failed_worker=str(getattr(env,'work',work)))
    finally:
        env.close()
    write(work/'result.json', result)
    print(json.dumps({'capture':row['id'], 'training_ready':result['training_ready'],
                      'error':result.get('error')}), flush=True)
    return result


def validate(cfg):
    for field in ('target','max_decisions','encounters_per_seed','jobs'):
        if type(cfg.get(field)) is not int or cfg[field] < 1: raise ValueError('Positive integer required: '+field)
    seeds = cfg.get('seeds')
    if not isinstance(seeds,list) or not seeds or len(seeds)!=len(set(seeds)):
        raise ValueError('Unique discovery seeds required')
    for seed in seeds:
        if not isinstance(seed,str) or not seed.isdigit() or not 0<=int(seed)<2**64:
            raise ValueError('Seeds must be uint64 strings')


def resegment(previous, root, source, seeds):
    """Re-rank existing immutable discovery traces without rerunning games."""
    manifest=json.loads((previous/'manifest.json').read_text())
    if manifest['engine_sha256'] != sha(ENGINE) or manifest['source_rc_sha256'] != sha(source):
        raise ValueError('Discovery engine/source mismatch')
    for name in ('bench.py','bridge.lua','direct_transport.lua'):
        if manifest['tools'][name] != sha(HERE/name):
            raise ValueError('Discovery observation/transport mismatch: '+name)
    originals={r['seed']:r for r in json.loads((previous/'discoveries.json').read_text())}
    results=[]
    for seed in seeds:
        original=originals[seed];trace=Path(original['trace'])
        if sha(trace) != original['trace_sha256']: raise ValueError('Discovery trace mutated')
        segments=Segmenter(seed);decisions=0
        with trace.open() as stream:
            for i,line in enumerate(stream):
                row=json.loads(line)
                if i==0:segments.observe(row['observation'],0)
                decisions=i+1
                segments.observe(row['next_observation'],decisions)
        segments.finish(decisions,original['outcome'])
        result=dict(original,candidates=segments.cases,resegmented_from=str(previous))
        work=root/('seed-'+seed);work.mkdir()
        write(work/'discovery.json',result);results.append(result)
    return results


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('config',type=Path); p.add_argument('output',type=Path)
    p.add_argument('--reuse-discovery',type=Path,
                   help='Re-segment hash-verified discovery traces from a previous run')
    a = p.parse_args(); cfg = json.loads(a.config.read_text()); validate(cfg)
    if 'partition' in cfg:
        split=json.loads(MANIFEST.read_text());assignments=partition_map(split)
        if cfg['partition'] not in ('train','validation','test'):
            raise ValueError('Invalid discovery partition')
        if any(assignments.get(s)!=cfg['partition'] for s in cfg['seeds']):
            raise ValueError('Discovery seed partition mismatch')
        cfg['split_provenance']=dict(manifest=split,sha256=sha(MANIFEST))
    source = (ROOT/cfg['rc']).resolve()
    if cfg.get('rc_sha256') and cfg['rc_sha256'] != sha(source): raise ValueError('RC hash mismatch')
    root = a.output.resolve(); root.mkdir(parents=True, exist_ok=False)
    frozen = root/'source.rc'; shutil.copy2(source, frozen)
    write(root/'config.json', cfg)
    write(root/'manifest.json', dict(engine_sha256=sha(ENGINE), source_rc_sha256=sha(frozen),
        tools={name:sha(HERE/name) for name in ('mine_encounters.py','bench.py','bridge.lua','direct_transport.lua')},
        reuse_discovery=str(a.reuse_discovery.resolve()) if a.reuse_discovery else None,
        scope='Instrumented baseline discovery; not proof of unchanged native full-run trajectory.'))
    discovery_root=root/'discovery'; discovery_root.mkdir()
    collection_root=root/'collection'; collection_root.mkdir()
    with ThreadPoolExecutor(max_workers=cfg['jobs']) as pool:
        discoveries=(resegment(a.reuse_discovery.resolve(),discovery_root,frozen,cfg['seeds'])
            if a.reuse_discovery else
            list(pool.map(lambda seed:discover(discovery_root,frozen,seed,cfg),cfg['seeds'])))
        write(root/'discoveries.json', discoveries)
        candidates=select(discoveries,cfg['target']); write(root/'candidates.json',candidates)
        results=list(pool.map(lambda row:capture(collection_root,frozen,row), candidates))
    write(collection_root/'catalog.json',results)
    index=build([collection_root],root/'dataset')
    summary=dict(requested=cfg['target'], discovered=sum(len(d['candidates']) for d in discoveries),
        selected=len(candidates), captured=sum((Path(r['case'])/'checkpoint.cs').exists() for r in results),
        training_ready=sum(r['training_ready'] for r in results),
        quarantined=sum(not r['training_ready'] for r in results), transitions=index['transitions'],
        discovery_outcomes={d['seed']:d['outcome'] for d in discoveries},
        dataset=str(root/'dataset/index.json'))
    write(root/'summary.json',summary); print(json.dumps(summary),flush=True)
    return 0 if summary['captured'] >= cfg['target'] else 1


if __name__ == '__main__': raise SystemExit(main())
