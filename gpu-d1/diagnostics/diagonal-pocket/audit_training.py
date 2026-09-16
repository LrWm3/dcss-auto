"""Count the diagonal-only dead-end motif in the 256 training floor layouts."""
import hashlib
import json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
manifest=json.loads((ROOT/'learning-runs/vision15-clumps-30m/manifest.json').read_text())
corpus=Path(manifest['corpus'])/'train';rows=[]
for name in manifest['maps']['train']:
 with (corpus/name).open('rb') as f:f.seek(28);raw=f.read(5600)
 floor=np.frombuffer(raw,np.uint8).reshape(70,80);pad=np.pad(floor,1);count=np.zeros_like(floor);diagonal=np.zeros_like(floor)
 for dx,dy in [(0,-1),(1,0),(0,1),(-1,0),(1,-1),(1,1),(-1,1),(-1,-1)]:
  neighbor=pad[1+dy:71+dy,1+dx:81+dx];count+=neighbor
  if dx and dy:diagonal+=neighbor
 matches=(floor>0)&(count==1)&(diagonal==1)
 rows.append(dict(map=name,count=int(matches.sum()),floor_sha256=hashlib.sha256(raw).hexdigest()))
result=dict(definition='Floor tile with exactly one walkable 8-neighbor, diagonally located',maps=len(rows),maps_with_motif=sum(r['count']>0 for r in rows),total_motif_tiles=sum(r['count'] for r in rows),rows=rows)
(ROOT/'results/diagonal-pocket-training-audit.json').write_text(json.dumps(result,indent=2)+'\n')
print({k:v for k,v in result.items() if k!='rows'})
