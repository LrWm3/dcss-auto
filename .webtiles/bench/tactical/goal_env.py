"""Versioned derived checkpoints; originals and historical adapters stay intact."""
import json
import shutil
from pathlib import Path
from bench import Environment, ACTIONS, HERE, sha

GOAL_ACTIONS={**ACTIONS,'safety':'goal_safety','up':'CMD_GO_UPSTAIRS'}

def derive(case, destination):
    case=Path(case); destination=Path(destination)
    meta=json.loads((case/'case.json').read_text())
    for name,key in [('trial.rc','rc_sha256'),('checkpoint.cs','save_sha256')]:
        if sha(case/name)!=meta[key]: raise ValueError('Parent checksum mismatch')
    source=(case/'trial.rc').read_text()
    needle='  return "\\nTBJSON "..json(state).."\\n"'
    if source.count(needle)!=1: raise ValueError('Unrecognized bridge')
    source=source.replace(needle,'  goal_observation(state)\n'+needle)
    needle='    elseif action=="berserk" then'
    if source.count(needle)!=1: raise ValueError('Unrecognized dispatch')
    source=source.replace(needle,'    elseif action=="goal_safety" then goal_safety()\n'
        '    elseif action=="CMD_GO_UPSTAIRS" then crawl.sendkeys("<")\n'+needle)
    at=source.rfind('\n>')
    if at<0: raise ValueError('No Lua block')
    source=source[:at]+'\n'+(HERE/'goal_bridge.lua').read_text()+source[at:]
    destination.mkdir(parents=True,exist_ok=False)
    shutil.copy2(case/'checkpoint.cs',destination/'checkpoint.cs')
    (destination/'trial.rc').write_text(source)
    meta.update(parent=str(case.resolve()),parent_rc_sha256=meta['rc_sha256'],
                rc_sha256=sha(destination/'trial.rc'),goal_version=1,
                goal_bridge_sha256=sha(HERE/'goal_bridge.lua'))
    # New schema/behavior needs its own validation; never inherit readiness.
    meta['training_ready']=False
    (destination/'case.json').write_text(json.dumps(meta,indent=2)+'\n')
    return destination

class GoalEnvironment(Environment):
    def step(self,action):
        if action not in GOAL_ACTIONS: raise ValueError(action)
        before=self.state
        if before.get('terminal'): raise RuntimeError('Terminal episode')
        if not self.direct_transport: raise ValueError('Direct transport required')
        self.child.send(chr(97+list(GOAL_ACTIONS).index(action)))
        after=self.await_state(expected_seq=before['seq']+1)
        self.state=after
        with (self.work/'transitions.jsonl').open('a') as f:
            f.write(json.dumps(dict(observation=before,action=action,next_observation=after,
                terminated=after.get('terminal')=='death',
                turn_delta=after.get('turn',before['turn'])-before['turn']))+'\n')
        return after
