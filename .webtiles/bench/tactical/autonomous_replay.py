"""Replay recorded decisions without per-decision console input; compare states."""
import argparse
import json
from pathlib import Path
from bench import Environment, ACTIONS
from verify_resume import normalized

def run(case, reference, output, dump_each=False):
    output.mkdir(parents=True,exist_ok=False)
    rows=[json.loads(x) for x in reference.read_text().splitlines()]
    commands=[ACTIONS[r['action']] for r in rows]
    assert 'baseline' not in commands
    env=Environment(output)
    try:
        env.reset(case)
        code='''
        AUTO_ROWS={}; AUTO_INDEX=1
        local snapshot=tactical_dump
        function tactical_dump() return "\\nAUTOTRACE "..table.concat(AUTO_ROWS,"\\nAUTOTRACE ").."\\n" end
        local commands=COMMANDS
        function ready()
          AUTO_ROWS[#AUTO_ROWS+1]=snapshot():match("TBJSON (.*)\\n")
          DUMP_EACH
          local action=commands[AUTO_INDEX]; AUTO_INDEX=AUTO_INDEX+1
          if not action then
            ready=function() end; crawl.dump_char(); crawl.mpr("AUTOREPLAY DONE"); return
          end
          if action=="berserk" then you.activate_ability("Berserk",0,0)
          else crawl.do_commands({action}) end
        end
        '''.replace('COMMANDS','{'+','.join(json.dumps(a) for a in commands)+'}').replace(
            'DUMP_EACH','crawl.dump_char()' if dump_each else '')
        env.console(' '.join(code.splitlines()))
        outcome=env.child.expect_exact(['AUTOREPLAY DONE','You die...'],timeout=60)
        if outcome:
            import time
            time.sleep(0.2)
            path=next((env.work/'morgue').glob('morgue-*.txt'))
        else:path=env.work/'morgue/TacticalEustachio.txt'
        dump=path.read_text()
        states=[json.loads(x.removeprefix('AUTOTRACE ')) for x in dump.splitlines() if x.startswith('AUTOTRACE ')]
        expected=[r['observation'] for r in rows]+[rows[-1]['next_observation']]
        mismatches=[i for i,(a,b) in enumerate(zip(states,expected)) if normalized(a)!=normalized(b)]
        result=dict(states=len(states),expected=len(expected),mismatches=mismatches,worker=str(env.work),
                    outcome='death' if outcome else 'finished')
        result['passed']=not outcome and len(states)==len(expected) and not mismatches
        (output/'states.json').write_text(json.dumps(states)+'\n')
        (output/'results.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result),flush=True)
        return result
    finally:env.close()

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--case',required=True,type=Path)
    p.add_argument('--reference',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--dump-each',action='store_true')
    a=p.parse_args();result=run(a.case,a.reference,a.output,a.dump_each)
    raise SystemExit(0 if result['passed'] else 1)
