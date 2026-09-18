"""Run symbolic feed-forward and GRU screens sequentially with bounded artifacts."""
import subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];OUT=ROOT/'learning-runs/remembered-grid'
if __name__=='__main__':
    for kind in ['ff','gru']:
        print('starting',kind,flush=True)
        with (OUT/f'symbolic-{kind}.log').open('w') as log:
            subprocess.run([str(ROOT/'.venv/bin/python'),str(HERE/'symbolic_run.py'),'--kind',kind,'--updates','12000'],stdout=log,stderr=subprocess.STDOUT,check=True)
        print('finished',kind,flush=True)
