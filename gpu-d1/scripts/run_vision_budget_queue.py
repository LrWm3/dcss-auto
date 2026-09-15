"""Run the reviewed vision budget comparisons sequentially; stop on any failure."""
import fcntl
import json
from pathlib import Path
import signal
import subprocess
import sys
from datetime import datetime

plan_path=Path(sys.argv[1]).resolve()
plan=json.loads(plan_path.read_text())
child=None
stopping=False

def stop(signum, _):
    global stopping
    stopping=True
    if child is not None and child.poll() is None:
        child.send_signal(signum)

for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,stop)
status_path=plan_path.with_name(plan_path.stem+'-status.json')
def status(**values):
    values['updated']=datetime.now().astimezone().isoformat()
    tmp=status_path.with_suffix('.tmp')
    tmp.write_text(json.dumps(values,indent=2)+'\n');tmp.replace(status_path)

with plan_path.with_suffix('.lock').open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    for index,job in enumerate(plan['jobs']):
        if stopping:break
        status(state='running',index=index,name=job['name'],completed=index,total=len(plan['jobs']))
        print('Starting',job['name'],flush=True)
        with Path(job['log']).open('a') as log:
            child=subprocess.Popen(job['command'],cwd=plan['cwd'],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
            code=child.wait()
        if code or stopping:
            status(state='stopped',index=index,name=job['name'],exit_code=code,completed=index,total=len(plan['jobs']))
            sys.exit(code or 130)
        result=json.loads(Path(job['result']).read_text())
        if result['decisions']<30_000_000:raise RuntimeError('Incomplete result: '+job['name'])
        print('Finished',job['name'],result['decisions'],flush=True)
    if stopping:sys.exit(130)
    status(state='complete',completed=len(plan['jobs']),total=len(plan['jobs']))
