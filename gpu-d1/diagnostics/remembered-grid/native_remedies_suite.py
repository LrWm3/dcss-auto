"""Sequential GPU jobs; stop the screen if any check/run fails."""
import subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
for arm in ('audit','control','balanced','exact'):
    with (ROOT/'learning-runs/remembered-grid'/f'native-remedy-{arm}.log').open('w') as log:
        subprocess.run([str(ROOT/'.venv/bin/python'),str(HERE/'native_remedies.py'),'--arm',arm],stdout=log,stderr=subprocess.STDOUT,check=True)
    print('completed',arm,flush=True)
