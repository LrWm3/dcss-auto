"""Run the two PPO continuations serially, failing closed if either job fails."""
import fcntl,json,subprocess,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];OUT=ROOT/'learning-runs/remembered-grid/route-threat'

def main():
    lock=(OUT/'ppo-suite.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    report=dict(finished=False,jobs=[]);start=time.monotonic();path=ROOT/'results/route-threat-ppo-suite.json'
    for arm in ['visible','memory']:
        print('launch',arm,flush=True);t=time.monotonic()
        command=[sys.executable,str(HERE/'route_threat_ppo.py'),'--arm',arm,'--decisions','500000']
        if (OUT/f'route-threat-ppo-{arm}/latest.pt').exists():command+=['--resume']
        with (OUT/f'ppo-{arm}.log').open('a') as f:
            subprocess.run(command,stdout=f,stderr=subprocess.STDOUT,check=True)
        result=json.loads((ROOT/'results'/f'route-threat-ppo-{arm}.json').read_text());assert result['finished']
        report['jobs'].append(dict(arm=arm,wall_seconds=time.monotonic()-t,last=result['history'][-1]));path.write_text(json.dumps(report,indent=2)+'\n');print('completed',arm,flush=True)
    report['finished']=True;report['wall_seconds']=time.monotonic()-start;path.write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':main()
