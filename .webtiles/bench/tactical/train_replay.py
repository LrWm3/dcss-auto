"""Small linear, DQfD-inspired pilot; not a reproduction of deep DQfD."""
import argparse
import copy
import json
import random
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from bench import ENGINE, sha
from tactical_options import Tactic
from train_encounters import features, load_cases, run_episode, validate, value, write
from train_teacher import imitate


def credit(result):
    """Bounded RC-followup outcome, not merely disappearance from sight."""
    end=result.get('handoff',{}).get('outcome',result['outcome'])
    if end=='death': return -1.
    if end=='floor_change': return 1.  # Progress, not proof of floor clearance.
    if end=='budget_alive' and result['handoff'].get('recovered_at_end'): return 1.
    return 0.


def credited(rows,result,n=5):
    rows=copy.deepcopy(rows)
    if not rows: return rows
    # The task includes a bounded fixed-RC continuation. Unfinished budgets are
    # neutral terminal outcomes of this finite-horizon task, not infinite RL.
    rows[-1].update(reward=credit(result),end=True)
    for i,row in enumerate(rows):
        tail=rows[i:min(len(rows),i+n)]
        row.update(n_reward=sum(t['reward'] for t in tail),
                   n_end=tail[-1]['end'],n_features=tail[-1]['next_features'],
                   n_allowed=tail[-1]['next_allowed'])
    return rows


class Replay:
    def __init__(self,demos,seed=42):
        self.demos=copy.deepcopy(demos);self.online=deque(maxlen=20000)
        self.model={};self.target={};self.rng=random.Random(seed);self.updates=0

    def adjust(self,action,f,error,rate=.03):
        scale=rate*max(-2.,min(2.,error))/max(1.,sum(x*x for x in f.values()))
        w=self.model.setdefault(action,{})
        for k,x in f.items(): w[k]=w.get(k,0.)+scale*x

    def bootstrap(self,f,allowed,end):
        if end or not allowed: return 0.
        a=max(allowed,key=lambda a:value(self.model,a,f))
        return value(self.target,a,f)

    def learn(self,batches):
        for _ in range(batches):
            for j in range(32):
                demo=not self.online or j%2==0
                row=self.rng.choice(self.demos if demo else list(self.online))
                f=row['features'];a=row['action']
                one=row['reward']+self.bootstrap(row['next_features'],row['next_allowed'],row['end'])
                multi=row['n_reward']+self.bootstrap(row['n_features'],row['n_allowed'],row['n_end'])
                self.adjust(a,f,(one+multi)/2-value(self.model,a,f))
                if demo:
                    others=[b for b in row['allowed'] if b!=a]
                    if others:
                        b=max(others,key=lambda b:value(self.model,b,f))
                        loss=.1+value(self.model,b,f)-value(self.model,a,f)
                        if loss>0:
                            self.adjust(a,f,loss);self.adjust(b,f,-loss)
            self.updates+=1
            if self.updates%25==0: self.target=copy.deepcopy(self.model)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('config',type=Path);p.add_argument('output',type=Path)
    args=p.parse_args();cfg=json.loads(args.config.read_text());validate(cfg)
    if not cfg.get('hazard_shield') or cfg['gamma']!=1 or not cfg.get('handoff_steps'):
        raise ValueError('This finite-horizon pilot requires shield, gamma=1 and RC followup')
    (train,evaluation),index=load_cases(cfg)
    root=args.output.resolve();root.mkdir(parents=True,exist_ok=False)
    write(root/'config.json',cfg)
    write(root/'manifest.json',dict(engine_sha256=sha(ENGINE),dataset_sha256=sha(index),
        sources={n:sha(Path(__file__).parent/n) for n in
                 ('train_replay.py','train_encounters.py','train_teacher.py','tactical_options.py','bench.py','mine_encounters.py')},
        train=train,validation=evaluation,production_export=False))
    results=[]

    def run(phase,entry,policy,model,number,epsilon=0.):
        work=root/f'{phase}-{policy}-{number:03d}';work.mkdir();rows=[]
        rng=random.Random(cfg['random_seed']+number);before=copy.deepcopy(model)
        def select(state,memory,allowed):
            if rng.random()<epsilon: return rng.choice(allowed)
            f=features(state,memory)
            return max(allowed,key=lambda a:value(model,a,f))
        r=run_episode(entry,work,policy,model,rng,cfg,training=False,
            controller=Tactic('retreat') if policy=='retreat' else None,
            selector=select if policy not in ('baseline','retreat') else None,transitions=rows)
        assert model==before,'Rollout mutated frozen weights'
        if r['outcome']=='harness_error' or r.get('handoff',{}).get('outcome')=='harness_error':
            raise RuntimeError(str(r))
        r.update(phase=phase,split='train' if entry in train else 'validation',audited_credit=credit(r))
        rows=credited(rows,r)
        write(work/'credited-transitions.json',rows);write(work/'audited-result.json',r)
        print(json.dumps(r),flush=True)
        return r,rows

    demos=[]
    for i,e in enumerate(train):
        r,rows=run('teacher',e,'retreat',{},i);results.append(r)
        if credit(r)>0: demos.extend(rows)
    write(root/'demonstrations.json',demos)
    if not demos: raise ValueError('No audited successful demonstrations')
    imitation,accuracy=imitate(demos)
    learner=Replay(demos,cfg['random_seed']);learner.learn(cfg['pretrain_batches'])
    write(root/'imitation.json',imitation);write(root/'initial-q.json',learner.model)

    def evaluate(phase,models):
        tasks=[(e,p,m) for e in train+evaluation for p,m in models.items()]
        with ThreadPoolExecutor(max_workers=cfg['jobs']) as pool:
            futures=[pool.submit(run,phase,e,p,copy.deepcopy(m),i) for i,(e,p,m) in enumerate(tasks)]
            for f in futures: results.append(f.result()[0])
        write(root/'results.json',results)

    evaluate('initial',dict(baseline={},imitation=imitation,q=learner.model))
    for i in range(cfg['episodes']):
        r,rows=run('train',train[i%len(train)],'q',learner.model,i,cfg['epsilon'])
        results.append(r);learner.online.extend(rows);learner.learn(cfg['online_batches'])
        write(root/f'model-{i:03d}.json',learner.model);write(root/'results.json',results)
    evaluate('final',dict(q=learner.model))
    write(root/'model.json',learner.model)
    groups=[]
    for key in sorted({(r['phase'],r['split'],r['policy']) for r in results}):
        rows=[r for r in results if (r['phase'],r['split'],r['policy'])==key]
        groups.append(dict(phase=key[0],split=key[1],policy=key[2],count=len(rows),
            credits=dict(Counter(r['audited_credit'] for r in rows)),
            outcomes=dict(Counter(r['outcome'] for r in rows)),
            handoffs=dict(Counter(r['handoff']['outcome'] for r in rows if 'handoff' in r))))
    write(root/'summary.json',dict(completed=True,trials=len(results),demonstrations=len(demos),
        imitation_accuracy=accuracy,groups=groups,production_export=False))


if __name__=='__main__': main()
