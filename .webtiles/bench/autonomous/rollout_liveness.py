"""Short-horizon inactivity diagnostic, not a tactical reward or teacher gate."""
from collections import Counter
from pathlib import Path
import json
from observation_history import observed_displacement


class ActivityTracker:
    def __init__(self, initial, idle_limit=128):
        self.idle_limit=idle_limit;self.idle=0;self.max_idle=0
        self.wait_run=0;self.max_wait_run=0;self.counts=Counter();self.events=Counter()
        self.position=(0,0);self.visited={(initial.get('level'),0,0)}
        self.tracked=True;self.steps=0
        self.safe_idle=0

    def record(self, before, action, after):
        self.steps+=1;self.counts[action['kind']]+=1
        self.wait_run=self.wait_run+1 if action['kind']=='WAIT' else 0
        self.max_wait_run=max(self.max_wait_run,self.wait_run)
        p,q=before.get('player',{}),after.get('player',{})
        events=[]
        if before.get('level')!=after.get('level'):
            events.append('level_change');self.position=(0,0);self.tracked=True
        else:
            shift=observed_displacement(before,action,after)
            if shift is None:self.tracked=False
            elif self.tracked:
                self.position=tuple(a+b for a,b in zip(self.position,shift))
        if self.tracked:
            key=(after.get('level'),*self.position)
            if key not in self.visited:events.append('new_position');self.visited.add(key)
        if q.get('hp',0)>p.get('hp',0):events.append('healing')
        if q.get('mp',0)>p.get('mp',0):events.append('mp_recovery')
        if (after.get('score') or 0)>(before.get('score') or 0):events.append('score_gain')
        if len(after.get('known') or {})>len(before.get('known') or {}):events.append('exploration')
        # Status/resource changes can make waiting useful. Merely advancing the
        # turn counter, losing HP, or changing the previous-action record cannot.
        for key in ('berserk','confused','poisoned','on_fire','slowed','exhausted',
                    'teleporting','caught','petrifying','mesmerised'):
            if p.get(key) and not q.get(key):events.append('status_cleared')
        if before.get('inventory')!=after.get('inventory'):events.append('inventory_change')
        if events:self.idle=0
        else:self.idle+=1
        self.max_idle=max(self.max_idle,self.idle);self.events.update(events)
        # Claim inactivity only in an unthreatened, stable situation. A fight or
        # ongoing impairment is inconclusive here, not evidence that WAIT is bad.
        safe=(after.get('safe') is True and not after.get('monsters') and
              not any(q.get(k) for k in ('confused','poisoned','on_fire','slowed',
                  'exhausted','teleporting','caught','petrifying','mesmerised')))
        self.safe_idle=self.safe_idle+1 if safe and not events else 0
        return self.safe_idle>=self.idle_limit and (self.tracked or self.wait_run>=self.idle_limit)

    def summary(self):
        return {'steps':self.steps,'action_counts':dict(self.counts),
                'progress_events':dict(self.events),'max_no_progress_run':self.max_idle,
                'max_consecutive_waits':self.max_wait_run,'position_tracking':self.tracked}


def rollout_check(model_path,source,output,budget=256,idle_limit=128):
    from concurrent.futures import ThreadPoolExecutor
    from general_env import GeneralEnvironment
    from policy import Policy
    from bootstrap_repair import write
    source,output=Path(source),Path(output);output.mkdir(parents=True,exist_ok=True)
    cases=json.loads((source/'round-00/validation/results.json').read_text())
    config={'model':str(Path(model_path).resolve()),'source':str(source.resolve()),
            'budget':budget,'idle_limit':idle_limit}
    if (output/'config.json').exists() and json.loads((output/'config.json').read_text())!=config:
        raise ValueError('rollout resume configuration mismatch')
    write(output/'config.json',config)
    def run(pair):
        i,r=pair;result_file=output/f'case-{i}.json'
        if result_file.exists():return json.loads(result_file.read_text())
        checkpoint=Path(r['resume_checkpoint'])
        if not checkpoint.is_absolute():checkpoint=Path(__file__).resolve().parents[3]/checkpoint
        try:
            policy,_=Policy.from_checkpoint(model_path,epsilon=0)
            with GeneralEnvironment(output/f'game-{i}',data_role='diagnostic') as env:
                env.record_events=False;state=env.launch(checkpoint)
                initial={k:state.get(k) for k in ('score','level','turn')}
                tracker=ActivityTracker(state,idle_limit);stalled=False
                for _ in range(budget):
                    if state.get('terminal'):break
                    index,action=policy.choose(state);after=env.step(index)
                    stalled=tracker.record(state,action,after);state=after
                    if stalled:break
                result={'seed':r['seed'],'stalled':stalled,'initial':initial,
                        'final':{k:state.get(k) for k in ('score','level','turn','terminal')},
                        **tracker.summary()}
                result['active']=not stalled and bool(tracker.events)
        except Exception as exc:
            result={'seed':r['seed'],'error':repr(exc),'active':False}
        write(result_file,result);return result
    write(output/'status.json',{'phase':'checking_rollout_liveness'})
    with ThreadPoolExecutor(max_workers=5) as pool:results=list(pool.map(run,enumerate(cases)))
    active=sum(r['active'] for r in results)
    check={'passed':len(results)==5 and active>=4 and not any('error' in r for r in results),
           'active_cases':active,'total':len(results),'budget':budget,'idle_limit':idle_limit,
           'scope':'liveness only; terminal outcomes are recorded, not evidence of tactical quality',
           'results':results}
    write(output/'results.json',check);write(output/'status.json',{'phase':'complete','check':check})
    return check
