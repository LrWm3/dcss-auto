"""Validate the resume-greeting engine patch against an uninterrupted trace.

Creates an explicitly migrated case; never changes the original or disables the
environment's engine-hash checks. Large verification artifacts stay local.
"""
import argparse
import json
import shutil
from pathlib import Path

import bench


def normalized(state):
    state=dict(state)
    for key in ('seq','messages'):
        state.pop(key,None)
    # Death may be detected through the terminal or a private morgue. Paths and
    # dump checksums are provenance, not gameplay state, and vary across resets.
    if state.get('terminal')=='death':
        for key in ('evidence','evidence_sha256'):
            state.pop(key,None)
    for key in ('monsters','inventory'):
        if key in state:
            state[key]=sorted(json.dumps(v,sort_keys=True) for v in state[key].values())
    return state


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine',required=True,type=Path)
    parser.add_argument('--case',required=True,type=Path)
    parser.add_argument('--reference',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    bench.ENGINE=args.engine.resolve()
    output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=False)
    source=args.case.resolve()
    metadata=json.loads((source/'case.json').read_text())
    for filename,field in [('checkpoint.cs','save_sha256'),('trial.rc','rc_sha256')]:
        assert bench.sha(source/filename)==metadata[field], f'{filename} checksum mismatch'
    migrated=output/'case'
    shutil.copytree(source,migrated)
    metadata.update(captured_engine_sha256=metadata['engine_sha256'],
        engine_sha256=bench.sha(bench.ENGINE),parent_case=str(source),
        migration_reason='Resume-only god greeting moved to UI RNG; save bytes unchanged',
        fidelity='pending equivalence verification')
    (migrated/'case.json').write_text(json.dumps(metadata,indent=2)+'\n')
    reference=[json.loads(line) for line in args.reference.read_text().splitlines()]
    warmup=metadata.get('warmup_decisions',0)
    prefix,reference=reference[:warmup],reference[warmup:]
    assert reference, 'No reference decisions after checkpoint'
    summary={'engine_sha256':bench.sha(bench.ENGINE),'case':str(migrated),
             'reference':str(args.reference.resolve()),
             'reference_sha256':bench.sha(args.reference),'trials':[]}
    for mode in ('loaded','loaded-repeat','fresh'):
        env=bench.Environment(output)
        trial={'mode':mode,'matched':0,'passed':False}
        try:
            initial=env.launch() if mode=='fresh' else env.reset(migrated)
            if mode=='fresh':
                for row in prefix:
                    initial=env.step(row['action'])
                    assert normalized(initial)==normalized(row['next_observation']), 'Warmup differs'
            assert normalized(initial)==normalized(reference[0]['observation']), 'Initial state differs'
            for index,row in enumerate(reference):
                after=env.step(row['action'])
                assert normalized(after)==normalized(row['next_observation']), f'Diverged at decision {index+1}'
                trial['matched']=index+1
            trial.update(passed=True,result=after.get('terminal','alive'))
        except Exception as exc:
            trial['error']=str(exc)
            raise
        finally:
            trial['worker']=str(env.work)
            env.close()
            summary['trials'].append(trial)
            (output/'verification.json').write_text(json.dumps(summary,indent=2)+'\n')
            print(json.dumps(trial),flush=True)
    metadata['fidelity']=f'{len(reference)}-decision trajectory matches uninterrupted reference, including its endpoint'
    (migrated/'case.json').write_text(json.dumps(metadata,indent=2)+'\n')


if __name__=='__main__':
    main()
