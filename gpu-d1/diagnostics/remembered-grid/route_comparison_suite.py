"""Serial GPU queue, with an automatically generated comparison artifact."""
import json,subprocess,time
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];OUT=ROOT/'learning-runs/remembered-grid'
start=time.monotonic()
for arm in ['oracle','random','onepass','recurrent','planner']:
    with (OUT/f'route-comparison-{arm}.log').open('w') as log:
        subprocess.run([str(ROOT/'.venv/bin/python'),str(HERE/'route_comparison.py'),'--arm',arm],stdout=log,stderr=subprocess.STDOUT,check=True)
    print('completed',arm,flush=True)
rows={}
for arm in ['oracle','random','onepass','recurrent','planner']:
    r=json.loads((ROOT/'results'/f'route-comparison-{arm}.json').read_text());assert r['finished']
    rows[arm]={k:v['summary'] for k,v in r.items() if k in ['middle_validation','longer_validation','middle_test','longer_test']}
    if 'selected' in r:rows[arm]['selected_step']=r['selected']['step'];rows[arm]['training_seconds']=r['history'][-1]['training_seconds'];rows[arm]['training_decisions']=r['history'][-1]['decisions']
report=dict(finished=True,wall_seconds=time.monotonic()-start,results=rows,scope='Learned arms are validation-selected. All arms evaluated on identical held-out test cases. Observed terrain only and one physical step per decision. Not PPO.')
(ROOT/'results/route-comparison-summary.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
