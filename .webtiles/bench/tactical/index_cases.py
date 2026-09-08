"""Build a hash-pinned dataset index; exclude unverified captures and repeats."""
import argparse
import json
from pathlib import Path
from bench import sha


def build(roots,output,namespace=False):
    labels=[(root.parent.name+'/'+root.name if namespace else root.name) for root in roots]
    if len(labels)!=len(set(labels)):
        raise ValueError('Duplicate collection names; use unique parent names and --namespace')
    output.mkdir(parents=True,exist_ok=False)
    index={'schema_version':1,'cases':[],'transitions':0,
           'split_policy':'Group by seed; related checkpoints and repeats must never cross splits.',
           'scope':'Verified against uninterrupted instrumented replay, not proof of historical full-game equivalence.'}
    with (output/'transitions.jsonl').open('x') as data:
        for root,label in zip(roots,labels):
            for path in sorted(root.glob('*/result.json')):
                result=json.loads(path.read_text())
                entry=dict(id=label+'/'+result['id'],seed=result['seed'],split_group=result['seed'],
                    result=str(path.resolve()),result_sha256=sha(path),
                    eligible=result.get('training_ready',False),
                    fidelity=result.get('uninterrupted_fidelity'),
                    repeatability=result.get('repeatability'),error=result.get('error'))
                case=Path(result['case'])
                if (case/'case.json').exists():
                    metadata=json.loads((case/'case.json').read_text())
                    entry.update(case=str(case),engine_sha256=metadata['engine_sha256'],
                        save_sha256=sha(case/'checkpoint.cs'),rc_sha256=sha(case/'trial.rc'),
                        initial=result.get('initial'))
                    if entry['save_sha256']!=metadata['save_sha256'] or entry['rc_sha256']!=metadata['rc_sha256']:
                        raise ValueError('Checkpoint mutated: '+str(case))
                if entry['eligible']:
                    # Keep one baseline rollout, not the verification repeats.
                    trial=result['trials'][0];trace=Path(trial['worker'])/'transitions.jsonl'
                    if sha(trace)!=trial['transitions_sha256']:raise ValueError('Trace mutated')
                    entry.update(outcome=trial['outcome'],decisions=trial['decisions'])
                    rows=[json.loads(line) for line in trace.read_text().splitlines()]
                    if len(rows)!=trial['decisions']:raise ValueError('Trace length mismatch')
                    for row in rows:
                        row.update(case_id=entry['id'],split_group=entry['split_group'],seed=entry['seed'])
                        data.write(json.dumps(row,sort_keys=True)+'\n')
                    index['transitions']+=len(rows)
                index['cases'].append(entry)
    index['transitions_file']=str((output/'transitions.jsonl').resolve())
    index['transitions_sha256']=sha(output/'transitions.jsonl')
    (output/'index.json').write_text(json.dumps(index,indent=2)+'\n')
    return index


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('output',type=Path);p.add_argument('roots',nargs='+',type=Path)
    p.add_argument('--namespace',action='store_true',help='Prefix case IDs with dataset directory names')
    a=p.parse_args();result=build(a.roots,a.output,namespace=a.namespace)
    print(json.dumps({'eligible':sum(c['eligible'] for c in result['cases']),
                      'total':len(result['cases']),'transitions':result['transitions']}))
