"""Create an explicitly labelled direct-input variant; preserve source case."""
import argparse
import json
import shutil
from pathlib import Path
from bench import HERE,sha

def migrate(source,destination,engine=None):
    metadata=json.loads((source/'case.json').read_text())
    assert sha(source/'checkpoint.cs')==metadata['save_sha256']
    assert sha(source/'trial.rc')==metadata['rc_sha256']
    shutil.copytree(source,destination)
    text=(source/'trial.rc').read_text()
    assert 'TB_DIRECT_TRANSPORT=true' not in text
    at=text.rfind('>')
    (destination/'trial.rc').write_text(text[:at]+'\n'+(HERE/'direct_transport.lua').read_text()+'\n'+text[at:])
    metadata.update(parent_case=str(source.resolve()),parent_rc_sha256=metadata['rc_sha256'],
                    rc_sha256=sha(destination/'trial.rc'),
                    migration_reason='Read action within ready, without extra input or macro-delay cycles',
                    fidelity='pending autonomous equivalence verification')
    if engine:
        metadata.update(parent_engine_sha256=metadata['engine_sha256'],engine_sha256=sha(engine))
        metadata['migration_reason']+='; character dumps isolated to UI RNG'
    (destination/'case.json').write_text(json.dumps(metadata,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('destination',type=Path)
    p.add_argument('--engine',type=Path)
    a=p.parse_args();migrate(a.source,a.destination,a.engine)
