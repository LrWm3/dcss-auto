#!/usr/bin/env python3
"""Independent native combat oracle and restricted native wait baseline."""
import json
import math
import pathlib
import subprocess

ROOT=pathlib.Path(__file__).resolve().parents[1]

def main():
    source=ROOT/'native/source'
    native=[str(source/'crawl-gpu-d1'),'-headless','-no-save','-no-gdb','-seed','1057','-script','gpu_bench',str(ROOT/'fixtures/fixture.bin')]
    compact=[str(ROOT/'build/bench'),'--fixture',str(ROOT/'fixtures/fixture.bin')]
    def read(command,cwd=None):
        p=subprocess.run(command,cwd=cwd,text=True,capture_output=True,check=True)
        return [json.loads(x) for x in p.stdout.splitlines() if x.startswith('{')]
    a=read(native+['6','300000','oracle'],source)
    b=read(compact+['--combat-check','--steps','300000'])
    for filename,rows in [('native-combat.jsonl',a),('compact-combat.jsonl',b)]:
        (ROOT/'results'/filename).write_text(''.join(json.dumps(x)+'\n' for x in rows))
    results=[]
    for x,y in zip(a,b):
        assert (x['kind'],x['preblocks'])==(y['kind'],y['preblocks'])
        n=x['samples'];entry={'kind':x['kind'],'preblocks':x['preblocks']}
        for key in ('blocks','dodges','damage'):
            p,q=x[key]/n,y[key]/n
            bound=[3,3,1,5,5,3][x['kind']] if key=='damage' else 1
            se=math.sqrt((p*(bound-p)+q*(bound-q))/n)
            assert abs(p-q)<=6*se+1e-12,(x,y,key)
            entry[key]={'native_mean':p,'compact_mean':q,'absolute_difference':abs(p-q),'conservative_z':abs(p-q)/se if se else 0}
        results.append(entry)
    (ROOT/'results/combat-validation.json').write_text(json.dumps(dict(samples_per_case=300000,cases=18,passed=True,
        criterion='Six standard errors for block/dodge; six conservative bounded-variance standard errors for mean damage. Independent RNG streams.',results=results),indent=2)+'\n')
    with (ROOT/'results/native-reference.jsonl').open('w') as out:
        for count,scenario,trials in [(1,'combat',1),(8,'combat',3),(8,'approach',3)]:
            for trial in range(trials):
                rows=read(native+[str(count),'100000',scenario],source)
                for row in rows:out.write(json.dumps(dict(row,trial=trial))+'\n')
                out.flush()
                print(rows,flush=True)
            row=read(compact+['--lifetimes','--monsters',str(count),'--scenario',scenario,'--steps','100000'])[0]
            out.write(json.dumps(row)+'\n');out.flush()

if __name__=='__main__':main()
