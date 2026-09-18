"""Serial, bounded-disk queue. A failed check or job stops subsequent jobs."""
import fcntl,json,subprocess,sys,time
from datetime import datetime,timezone
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
OUT=ROOT/'learning-runs/remembered-grid/route-threat'

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    lock=(OUT/'suite.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    start=time.monotonic();report=dict(started_utc=datetime.now(timezone.utc).isoformat(),finished=False,jobs=[])
    path=ROOT/'results/route-threat-suite.json'
    for arm in ['teacher','visible','memory']:
        log=OUT/f'{arm}.log';command=[sys.executable,str(HERE/'route_threat.py'),'--arm',arm,'--updates','2000']
        print('launch',arm,datetime.now(timezone.utc).isoformat(),flush=True)
        t=time.monotonic()
        with log.open('w') as f:subprocess.run(command,stdout=f,stderr=subprocess.STDOUT,check=True)
        result=json.loads((ROOT/'results'/f'route-threat-{arm}.json').read_text());assert result['finished']
        report['jobs'].append(dict(arm=arm,wall_seconds=time.monotonic()-t,selected=result.get('selected'),ordinary=result['ordinary']['groups'],pressure=result['pressure']['groups']))
        path.write_text(json.dumps(report,indent=2)+'\n');print('completed',arm,report['jobs'][-1],flush=True)
    report['finished']=True;report['wall_seconds']=time.monotonic()-start;path.write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':main()
