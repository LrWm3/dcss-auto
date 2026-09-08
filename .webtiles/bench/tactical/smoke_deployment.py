"""Fresh, uninterrupted D:5 handoff smoke tests in private game directories."""
import argparse
import concurrent.futures
import json
import os
import time
from pathlib import Path
import pexpect
from bench import ENGINE,sha

def trial(root,rc,seed,label):
    work=root/label;work.mkdir()
    for d in ('saves','morgue','macros'):(work/d).mkdir()
    source=rc.read_text();at=source.rfind('>')
    tail='''
    local smoke_ready=ready
    function ready()
      if you.branch()=="D" and you.depth()>=5 then
        BOT.paused=true; ready=function() end
        crawl.take_note("SMOKE reached D:5");crawl.dump_char();crawl.mpr("SMOKE DONE");return
      end
      smoke_ready()
    end
    '''
    tested=work/'trial.rc';tested.write_text(source[:at]+tail+'\n>\n')
    argv=['-name','TacticalSmoke','-rc',str(tested),'-seed',seed,'-no-player-bones']
    for option in ('species=Minotaur','background=Berserker','weapon=hand axe'):
        argv+=['-extra-opt-last',option]
    for opt,d in [('save_dir','saves'),('morgue_dir','morgue'),('macro_dir','macros')]:
        argv+=['-extra-opt-last',opt+'='+str(work/d)+'/']
    log=(work/'terminal.txt').open('w')
    child=pexpect.spawn(str(ENGINE),argv,cwd=str(ENGINE.parent),env={**os.environ,'TERM':'xterm'},
                        encoding='utf-8',codec_errors='replace',dimensions=(50,160),timeout=30)
    child.logfile_read=log
    result=dict(label=label,seed=seed,engine_sha256=sha(ENGINE),rc_sha256=sha(tested),worker=str(work))
    deadline=time.monotonic()+180
    last_tail=None
    try:
        while time.monotonic()<deadline:
            i=child.expect(['SMOKE DONE',r'You die\.\.\.',r'Hit .* to (?:continue|start)',
                            r'Press .* to (?:continue|start)',pexpect.TIMEOUT,pexpect.EOF],timeout=20)
            if i in (2,3):child.send(' ');continue
            if i==0:result['outcome']='reached_D5';break
            if i==1:result['outcome']='death';time.sleep(.2);break
            if i==5:result['outcome']='unexpected_exit';break
            if i==4:
                tail=child.before[-4000:]
                if tail!=last_tail:
                    last_tail=tail
                    continue
                # Two unchanged snapshots, not merely a pattern-match timeout.
                child.send('\x04');child.expect_exact('[Hit ESC to exit interpreter.]',timeout=5)
                child.send('crawl.dump_char(); crawl.mpr("SMOKE".." INSPECTED")\r')
                child.expect_exact('SMOKE INSPECTED',timeout=5)
                result['outcome']='paused';break
        else:result['outcome']='budget'
    except Exception as exc:result.update(outcome='harness_error',error=str(exc))
    finally:
        child.close(force=True);log.close()
        (work/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('rc',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();a.output=a.output.resolve();a.output.mkdir(parents=True,exist_ok=False)
    seeds=[(1,'6144198052690956201'),(3,'1760771545328102746')]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda v:trial(a.output,a.rc,v[1],'seed'+str(v[0])),seeds))
    (a.output/'results.json').write_text(json.dumps(results,indent=2)+'\n')
    print(json.dumps(results),flush=True)
