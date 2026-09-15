#!/usr/bin/env python3
"""Staged, sequential runs; all timings exclude startup and initial upload."""
import argparse
import datetime
import json
import math
import pathlib
import statistics
import subprocess
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]

def telemetry():
    return subprocess.run(['nvidia-smi','--query-gpu=name,temperature.gpu,power.draw,clocks.sm,clocks.mem,pstate',
                           '--format=csv,noheader'],text=True,capture_output=True).stdout.strip()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--stage',choices=['probe','matrix','launch','baselines','cpu12','sustained'],default='matrix')
    args=ap.parse_args()
    output=ROOT/'results'/f'{args.stage}.jsonl'
    configurations=[]
    def add(group,backend='thread',batch=2048,monsters=8,scenario='mixed',chunk=64,threads=1,heap=False,observe=False):
        c=locals().copy();configurations.append(c)
    if args.stage=='probe':
        for backend in ('cpu','thread','warp'):
            for heap in (False,True):
                add('probe',backend=backend,heap=heap,threads=6 if backend=='cpu' else 1)
    elif args.stage=='matrix':
        for b in (1,32,128,512,2048,8192,32768):
            add('batch',batch=b)
            add('batch',backend='warp',batch=b)
        for n in (1,8,32,64):
            for backend in ('cpu','thread','warp'):
                for heap in (False,True):
                    add('actors',backend=backend,monsters=n,heap=heap)
            add('actors',backend='cpu',threads=6,monsters=n)
        for scenario in ('quiet','approach','combat','mixed'):
            for backend in ('cpu','thread','warp'):
                add('workload',backend=backend,scenario=scenario,threads=6 if backend=='cpu' else 1)
        for backend in ('cpu','thread','warp'):
            for chunk in (1,64,256):
                for observe in (False,True):
                    add('launch',backend=backend,chunk=chunk,observe=observe,threads=6 if backend=='cpu' else 1)
    elif args.stage=='cpu12':
        for heap in (False,True):
            add('sustained',backend='cpu',threads=12,batch=8192,heap=heap)
    elif args.stage=='baselines':
        for n in (1,8,32,64):
            add('actors',backend='cpu',threads=6,monsters=n,heap=True)
        for scenario in ('combat', 'approach'):
            add('native-comparison',backend='cpu',scenario=scenario)
    elif args.stage=='launch':
        for backend in ('cpu','thread','warp'):
            for chunk in (1,64,256):
                for observe in (False,True):
                    add('launch',backend=backend,chunk=chunk,observe=observe,threads=6 if backend=='cpu' else 1)
    else:
        # Same batch/workload for sustained CPU and GPU comparisons.
        for backend,threads in (('cpu',1),('cpu',6),('thread',1),('warp',1)):
            add('sustained',backend=backend,threads=threads,batch=8192)
            if backend=='cpu':
                add('sustained',backend=backend,threads=threads,batch=8192,heap=True)
    with output.open('w') as out:
        for c in configurations:
            command=[str(ROOT/'build/bench'),'--fixture',str(ROOT/'fixtures/fixture.bin')]
            for key in ('backend','batch','monsters','scenario','chunk','threads'):
                command.extend(['--'+key,str(c[key])])
            if c['heap']:command.append('--heap')
            if c['observe']:command.append('--observe')
            def run(steps,trials):
                p=subprocess.run(command+['--steps',str(steps),'--trials',str(trials)],text=True,capture_output=True,check=True)
                return [json.loads(line) for line in p.stdout.splitlines()]
            pilot=run(64,1)[0]
            target=3.0 if args.stage=='sustained' else 0.15
            steps=min(65536,max(256,math.ceil(target/pilot['wall_s']*64/256)*256))
            if args.stage in ('sustained','cpu12'):
                # Exactly the same work and RNG trajectories on every backend.
                steps=4096
            temp_before=telemetry()
            rows=run(steps,3)
            temp_after=telemetry()
            for row in rows:
                row.update(group=c['group'],utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                           telemetry_before=temp_before,telemetry_after=temp_after)
                out.write(json.dumps(row)+'\n')
            out.flush()
            rate=statistics.median(r['waits_per_s'] for r in rows)
            print(f"{c['group']} {c['backend']} cpu={c['threads']} B={c['batch']} M={c['monsters']} {c['scenario']} heap={c['heap']} chunk={c['chunk']} obs={c['observe']}: {rate:,.0f}/s",flush=True)
    print(output)

if __name__=='__main__':main()
