#!/usr/bin/env python3
"""Re-export the chosen native seed, or repeat terrain-only seed selection."""
import argparse
import json
import pathlib
import subprocess

ROOT=pathlib.Path(__file__).resolve().parents[1]

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--search',action='store_true')
    args=ap.parse_args()
    source=ROOT/'native/source'
    rows=[]
    for seed in range(1001,2001) if args.search else [1057]:
        target=ROOT/'fixtures'/f'native-{seed}'
        subprocess.run([str(source/'crawl-gpu-d1'),'-headless','-no-save','-no-gdb','-seed',str(seed),'-script','gpu_export',str(target)],cwd=source,check=True)
        d=json.loads(target.with_suffix('.json').read_text())
        rows.append({'seed':seed,'unsupported_tiles':d['unsupported_tiles'],'map_marker_count':d.get('map_marker_count')})
        markers=target.with_suffix('.markers').read_text().splitlines()
        if not d['unsupported_tiles'] and all(line.split()[0]=='0' for line in markers):
            assert seed==1057, 'Selection changed: inspect native source/export before replacing the pinned fixture.'
            break
        if args.search:
            target.with_suffix('.json').unlink()
            target.with_suffix('.markers').unlink()
    else:raise RuntimeError('No eligible layout')
    if args.search:
        (ROOT/'fixtures/selection.json').write_text(json.dumps({'predicate':'First ascending seed from 1001 with only supported terrain; no timing used for selection.','candidates':rows},indent=2)+'\n')
    subprocess.run(['python3',str(ROOT/'scripts/compile_fixture.py')],check=True)

if __name__=='__main__':main()
