"""Paired old/fixed replay from privately copied, naturally stalled saves."""
import argparse
import concurrent.futures
import json
import shutil
from pathlib import Path
from bench import ROOT
from smoke_deployment import trial

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('fixed_rc',type=Path);p.add_argument('output',type=Path)
a=p.parse_args();root=a.output.resolve();root.mkdir(parents=True,exist_ok=False)
original=ROOT/'.webtiles/bench/batches/tactical-imitation-v2/tested.rc'
jobs=[]
for index,name,seed in [(2,'CodexTactV2B','13772526223844354029'),(4,'CodexTactV2D','17908030050512890810')]:
    save=root/(name+'.cs')
    shutil.copy2(ROOT/('crawl-0.35/crawl-ref/source/saves/'+name+'.cs'),save)
    for mode,rc in [('old',original),('fixed',a.fixed_rc.resolve())]:
        jobs.append((root,rc,seed,f'seed{index}-{mode}',True,save,name,13))
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    results=list(pool.map(lambda args:trial(*args),jobs))
(root/'results.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results),flush=True)
