"""Render transparent, outcome-labelled examples from the frozen evaluation."""
import json,torch
from runtime import OUT,ROOT,Env,SpatialPolicy
from maps import X0,Y0

@torch.no_grad()
def trace(model,split,scenario):
    e=Env(split,1);e.reset(torch.tensor([scenario],device='cuda'),labels=False)
    start=e.grid[0].cpu().clone();positions=[int(e.meta[0,0])];initial=int(e.meta[0,5])
    for _ in range(256):
        a=model(e.grid,e.mask,e.stats).argmax(-1);e.step(a,limit=256,labels=False);positions.append(int(e.meta[0,0]))
        if not e.active.any():break
    return start,e.grid[0].cpu(),positions,int(e.out[0,2]),int(e.out[0,5])-initial

def main():
    torch.set_num_threads(1);report=json.loads((OUT/'final.json').read_text());folder=OUT/'memory-spatial';ck=torch.load(folder/'best.pt',weights_only=False);model=SpatialPolicy().cuda();model.load_state_dict(ck['model'])
    rows=report['arms']['memory-spatial']['evaluations']['test_greedy']['rows']
    known=next(r for r in rows if r['kind']==0 and r['exit'] and r['goal_outside_local']);explore=next(r for r in rows if r['kind']==1 and r['exit'] and r['initial_known_stairs']==0)
    examples=[('Known stairs: first successful distant-goal test','test',known['scenario']),('Exploration: first successful initially hidden-goal test','test',explore['scenario']),('Paired history: remembered goal on branch A','probe',0),('Same local view/history: goal on branch B','probe',1)]
    svg=['<svg xmlns="http://www.w3.org/2000/svg" width="780" height="880" viewBox="0 0 780 880">','<rect width="780" height="880" fill="#ffffff"/>','<style>text{font-family:monospace;font-size:11px}</style>','<text x="20" y="22">Remembered-grid policy: no route hints or action overrides</text>','<text x="20" y="41">Final discovered terrain; blue = chosen route; green = start; gold = known stairs</text>']
    traces=[]
    for j,(title,split,scenario) in enumerate(examples):
        start,g,positions,success,turns=trace(model,split,scenario);ox=20+(j%2)*385;oy=90+(j//2)*390
        svg.append(f'<text x="{ox}" y="{oy-24}">{title}</text>');svg.append(f'<text x="{ox}" y="{oy-9}">scenario {scenario}: {"EXIT" if success else "FAIL"}, {turns} turns</text>')
        for y in range(32):
            for x in range(32):
                color='#eeeeee' if not(g[0,y,x] or g[1,y,x]) else '#4d5361' if g[1,y,x] else '#ffffff'
                if g[4,y,x]:color='#f4b942'
                svg.append(f'<rect x="{ox+x*10}" y="{oy+y*10}" width="10" height="10" fill="{color}"/>')
        pts=' '.join(f'{ox+(p%80-X0+.5)*10},{oy+(p//80-Y0+.5)*10}' for p in positions)
        svg.append(f'<polyline points="{pts}" fill="none" stroke="#2975cc" stroke-width="2" opacity=".8"/>')
        p=positions[0];svg.append(f'<circle cx="{ox+(p%80-X0+.5)*10}" cy="{oy+(p//80-Y0+.5)*10}" r="4" fill="#139449"/>')
        traces.append(dict(title=title,split=split,scenario=scenario,exit=success,turns=turns,positions=positions))
    svg+=['<text x="20" y="865">Illustrative successes are selected as labelled; aggregate results include all failures.</text>','</svg>']
    (ROOT/'results/remembered-grid-examples.svg').write_text('\n'.join(svg));(OUT/'example-traces.json').write_text(json.dumps(traces,indent=2))
if __name__=='__main__':main()
