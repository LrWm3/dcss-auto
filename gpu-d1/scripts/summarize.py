#!/usr/bin/env python3
"""Standard-library summary tables and a standalone SVG performance figure."""
import collections
import csv
import html
import json
import math
import pathlib
import statistics

ROOT=pathlib.Path(__file__).resolve().parents[1]

def main():
    rows=[]
    rerun=(ROOT/'results/launch.jsonl').exists()
    for name in ('matrix','launch','baselines','sustained','cpu12'):
        path=ROOT/'results'/f'{name}.jsonl'
        if path.exists():
            rows.extend(r for r in map(json.loads,path.read_text().splitlines()) if not(name=='matrix' and rerun and r['group']=='launch'))
    keys=('group','backend','threads','scheduler','scenario','batch','monsters','chunk','observe','steps')
    groups=collections.defaultdict(list)
    for r in rows:groups[tuple(r[k] for k in keys)].append(r)
    summary=[]
    for key,values in groups.items():
        r=values[0]
        v=dict(zip(keys,key))
        v.update(trials=len(values),waits_per_s=statistics.median(x['waits_per_s'] for x in values),
                 minimum=min(x['waits_per_s'] for x in values),maximum=max(x['waits_per_s'] for x in values),
                 mean_batch_step_us=statistics.median(x['wall_s'] for x in values)/r['steps']*1e6,
                 move_fraction=r['move_turns']/r['turns'],combat_fraction=r['combat_turns']/r['turns'],
                 actions_per_wait=r['actions']/r['turns'],attacks_per_wait=r['attacks']/r['turns'],
                 deaths_per_wait=r['deaths']/r['turns'],repairs_per_wait=r['repairs']/r['turns'],
                 device_bytes=r['device_bytes'])
        summary.append(v)
    (ROOT/'results/summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    with (ROOT/'results/summary.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(summary[0]));w.writeheader();w.writerows(summary)
    # Log/log scales make the small-batch costs and saturation visible together.
    svg=['<svg xmlns="http://www.w3.org/2000/svg" width="900" height="490" viewBox="0 0 900 490">',
         '<rect width="900" height="490" fill="white"/>',
         '<style>text{font-family:system-ui,sans-serif;fill:#222;font-size:13px}.grid{stroke:#ddd;stroke-width:1}</style>',
         '<text x="65" y="28" style="font-size:19px;font-weight:600">D:1 mixed-phase waiting — eight monsters per world</text>',
         '<text x="65" y="49">Median of three trials; 64 waits per kernel; real deaths and resets included</text>']
    def x(batch):return 90+math.log2(batch)/15*730
    def y(rate):return 400-(math.log10(rate)-4)/4*300
    for rate,label in ((1e4,'10k'),(1e5,'100k'),(1e6,'1M'),(1e7,'10M'),(1e8,'100M')):
        yy=y(rate);svg.append(f'<line class="grid" x1="90" x2="820" y1="{yy}" y2="{yy}"/><text x="80" y="{yy+4}" text-anchor="end">{label}</text>')
    for batch in (1,32,128,512,2048,8192,32768):
        xx=x(batch);svg.append(f'<line class="grid" x1="{xx}" x2="{xx}" y1="100" y2="400"/><text x="{xx}" y="422" text-anchor="middle">{batch:,}</text>')
    for backend,color,label in [('thread','#1976d2','Thread per world'),('warp','#d1495b','Warp per world')]:
        values=sorted((r for r in summary if r['group']=='batch' and r['backend']==backend),key=lambda r:r['batch'])
        points=' '.join(f"{x(r['batch']):.2f},{y(r['waits_per_s']):.2f}" for r in values)
        svg.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="3"/>')
        for r in values:svg.append(f'<circle cx="{x(r["batch"]):.2f}" cy="{y(r["waits_per_s"]):.2f}" r="4" fill="{color}"/>')
    for threads,color in ((1,'#626262'),(6,'#2b7a36')):
        candidates=[r for r in summary if r['group']=='sustained' and r['backend']=='cpu' and r['threads']==threads]
        if candidates:
            yy=y(max(r['waits_per_s'] for r in candidates));svg.append(f'<line x1="90" x2="820" y1="{yy}" y2="{yy}" stroke="{color}" stroke-dasharray="6 4"/><text x="815" y="{yy-6}" text-anchor="end" style="fill:{color}">CPU, {threads} worker(s), best scheduler, B=8,192</text>')
    svg.extend(['<text x="95" y="78" style="fill:#1976d2">● Thread per world</text>',
                '<text x="260" y="78" style="fill:#d1495b">● Warp per world</text>',
                '<text x="450" y="456" text-anchor="middle">Independent worlds in batch (log scale)</text>',
                '<text transform="translate(20 250) rotate(-90)" text-anchor="middle">Completed waits / second (log scale)</text>',
                '<text x="65" y="482">Quadro RTX 5000 Max-Q · i7-10750H · B=1 is contact-only; larger batches split contact/approach</text>',
                '</svg>'])
    (ROOT/'results/throughput.svg').write_text('\n'.join(svg)+'\n')
    print(f'{len(summary)} configurations summarized')

if __name__=='__main__':main()
