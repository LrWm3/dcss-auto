"""Run the established tactical suite against an explicit checkpoint pair."""
import argparse
import json
import os
import pathlib
import subprocess
import sys
from assets import ROOT


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--ordinary',type=pathlib.Path,required=True);ap.add_argument('--clumped',type=pathlib.Path,required=True);ap.add_argument('--prefix',required=True);args=ap.parse_args()
    config=ROOT/'learning-runs/tactical-next-assets'/f'{args.prefix}models.json'
    config.write_text(json.dumps(dict(ordinary=str(args.ordinary),mixed=str(args.clumped),result_prefix=args.prefix),indent=2)+'\n')
    env=os.environ|{'DCSS_DIAGNOSTIC_MODELS':str(config)}
    tasks=[('hallway',[],'hallway-retreat.json'),('hallway-six',[],'hallway-six-retreat.json'),('diagonal-pocket',[],'diagonal-pocket-retreat.json')]
    tasks += [('distant-pocket',['--distance',str(d)],f'distant-pocket-{d}-retreat.json') for d in [4,6]]
    for folder,flags,name in tasks:
        subprocess.run([sys.executable,str(ROOT/'diagnostics'/folder/'run.py'),*flags],env=env,check=True)
        before=json.loads((ROOT/'results'/name).read_text());after=json.loads((ROOT/'results'/(args.prefix+name)).read_text())
        for arm in ['hold_fight','retreat_fight']:assert before['arms'][arm]==after['arms'][arm],(name,arm)
    for label,path in [('ordinary',args.ordinary),('clumped',args.clumped)]:
        subprocess.run([sys.executable,str(pathlib.Path(__file__).with_name('evaluate_extra.py')),str(path),str(ROOT/'results'/f'{args.prefix}{label}-extra.json')],check=True)
    (ROOT/'results'/f'{args.prefix}complete.json').write_text(json.dumps(dict(scripted_controls_exact=True,ordinary=str(args.ordinary),clumped=str(args.clumped)),indent=2)+'\n')
if __name__=='__main__':main()
