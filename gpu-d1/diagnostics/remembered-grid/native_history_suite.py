"""Run matched short/full history screens sequentially; preserve all logs."""
import subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
for history in ('short','full'):
    name='native-history-'+history
    with (ROOT/'learning-runs/remembered-grid'/f'{name}.log').open('w') as log:
        subprocess.run([str(ROOT/'.venv/bin/python'),str(HERE/'native_remedies.py'),
                        '--arm','balanced','--replay-history',history,'--name',name],
                       stdout=log,stderr=subprocess.STDOUT,check=True)
    print('completed',history,flush=True)
