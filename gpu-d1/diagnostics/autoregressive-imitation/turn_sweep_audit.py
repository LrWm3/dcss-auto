"""Wait for the cost sweep, then replay all final policies with loop diagnostics."""
import json,pathlib,subprocess,sys,time
ROOT=pathlib.Path(__file__).resolve().parents[2]
status=ROOT/'learning-runs/autoregressive-turn-sweep/status.json'
while not status.exists() or json.loads(status.read_text())['status']!='complete':
 time.sleep(15)
results={}
for n in [0,1,3,10,30,100]:
 suite={0:'autoregressive-imitation-no-entropy',1:'autoregressive-turn-cost'}.get(n,'autoregressive-turn-sweep')
 result={0:'autoregressive-imitation-no-entropy',1:'autoregressive-turn-cost'}.get(n,'autoregressive-turn-sweep')
 output=f'autoregressive-turn-sweep-navigation-n{n}'
 args=[sys.executable,str(pathlib.Path(__file__).with_name('navigation_audit.py')),'--suite',suite,'--result',result,'--output',output,'--stages','1000448','--modes','type_greedy','sampled']
 if n>1:args+=['--job',f'turn-cost-n{n}-seed0','--sweep-n',str(n)]
 subprocess.run(args,check=True)
 results[str(n)]=json.loads((ROOT/'results'/f'{output}.json').read_text())
(ROOT/'results/autoregressive-turn-sweep-navigation.json').write_text(json.dumps(results,indent=2)+'\n')
print('Sweep navigation audit complete',flush=True)
