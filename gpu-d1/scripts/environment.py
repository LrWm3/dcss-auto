#!/usr/bin/env python3
"""Record hardware, build settings, source and fixture fingerprints."""
import datetime
import hashlib
import json
import pathlib
import subprocess

ROOT=pathlib.Path(__file__).resolve().parents[1]

def main():
    def capture(args):
        p=subprocess.run(args,text=True,capture_output=True)
        return dict(command=args,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr)
    data={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'commands':[capture(cmd) for cmd in [
              ['uname','-a'],['lscpu'],['nvidia-smi','-q'],['/usr/bin/nvcc','--version'],
              ['/usr/bin/g++-12','--version'],['g++','--version'],['git','rev-parse','HEAD']]],
          'cuda_flags':'-O3 -std=c++17 -arch=sm_75 -ccbin /usr/bin/g++-12 -Xcompiler -fopenmp -lineinfo',
          'native_cflags':(ROOT/'native/source/.cflags').read_text(),
          'native_cxxflags':(ROOT/'native/source/.cxxflags').read_text() if (ROOT/'native/source/.cxxflags').exists() else None,
          'hashes':{}}
    for pattern in ('src/*','scripts/*.py','fixtures/*','build/bench','native/source/crawl-gpu-d1'):
        for p in ROOT.glob(pattern):
            if p.is_file():data['hashes'][str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
    native=ROOT.parent/'crawl-0.35/crawl-ref/source'
    for name in ('dungeon.cc','ng-setup.cc','mon-data.h','mon-util.cc','mon-act.cc','monster.cc','attack.cc',
                 'melee-attack.cc','fight.cc','player.cc','actor.cc','item-prop.cc','player-reacts.cc','main.cc',
                 'pcg.cc','random.cc','los.cc','losglobal.cc','bitary.cc'):
        p=native/name
        if p.exists():data['hashes'][str(p.relative_to(ROOT.parent))]=hashlib.sha256(p.read_bytes()).hexdigest()
    (ROOT/'results/environment.json').write_text(json.dumps(data,indent=2)+'\n')

if __name__=='__main__':main()
