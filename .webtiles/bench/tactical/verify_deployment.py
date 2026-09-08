"""Fit on corrected transport, verify disabled adapter and fresh deployed actions."""
import argparse
import json
from pathlib import Path
from bench import Environment,sha,ENGINE
from learn import imitate
from export_model import export
from verify_resume import normalized

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--teacher',required=True,type=Path)
    p.add_argument('--baseline',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    model=a.output/'model.json';model.write_text(json.dumps(imitate([a.teacher]),indent=2)+'\n')
    active=a.output/'active.rc';export(model,active)
    disabled=a.output/'disabled.rc';source=active.read_text();at=source.rfind('>')
    disabled.write_text(source[:at]+'\nML_POLICY_DISABLED=true\n>\n')
    results=[]
    for mode,rc,reference in [('disabled',disabled,a.baseline),('active',active,a.teacher/'transitions.jsonl')]:
        rows=[json.loads(x) for x in reference.read_text().splitlines()]
        env=Environment(a.output,rc);result=dict(mode=mode,matched=0,engine_sha256=sha(ENGINE))
        try:
            state=env.launch()
            assert normalized(state)==normalized(rows[0]['observation']),'Fresh initial state differs'
            for i,row in enumerate(rows):
                state=env.step('baseline')
                assert normalized(state)==normalized(row['next_observation']),f'Divergence at {i+1}'
                result['matched']=i+1
            result.update(passed=True,outcome=state.get('terminal','alive'),turn=state.get('turn'))
        except Exception as exc:result.update(passed=False,error=str(exc))
        finally:
            result['worker']=str(env.work);env.close();results.append(result)
            (a.output/'results.json').write_text(json.dumps(results,indent=2)+'\n')
            print(json.dumps(result),flush=True)
    return all(r['passed'] for r in results)

if __name__=='__main__':raise SystemExit(0 if main() else 1)
