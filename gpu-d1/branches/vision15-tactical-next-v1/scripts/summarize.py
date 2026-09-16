"""Compare completed training variants and the shared tactical evaluations."""
import pathlib,json,statistics as st
R=pathlib.Path(__file__).resolve().parents[3];P=R/'results';read=lambda p:json.loads(p.read_text());avg=lambda xs:st.mean(xs)
rows=[]
for kind,step in [('baseline',30),('continue',50),('continue',75),('continue',100),('targeted',50),('targeted',75),('targeted',100),('enemy_set',30),('d4_exact',30)]:
 for placement,arm in [('ordinary','ordinary'),('clumped','mixed')]:
  seeds=[]
  for seed in range(3):
   if kind=='baseline':
    suite,name=(('vision15-seen-death4-30m','tiles_seen_death4-seed0') if placement=='ordinary' else ('vision15-clumps-30m','clumps_third-seed0')) if seed==0 else ('vision15-direction-seeds-30m',f'{"ordinary" if placement=="ordinary" else "clumps_third"}-seed{seed}')
    result=read(R/'learning-runs'/suite/'runs'/name/'result.json');final=result['final'];prefix='' if seed==0 else f'seed{seed}-noaug-';extra=read(P/f'tactical-next-baseline-{placement}-seed{seed}-extra.json')
   else:
    result=read(R/'learning-runs/vision15-tactical-next/runs'/f'{kind}_{placement}-seed{seed}'/'result.json')
    curve=read(R/'learning-runs/vision15-tactical-next/runs'/f'{kind}_{placement}-seed{seed}'/'curve.json');n=((step*1000000+32767)//32768)*32768;final=next(x for x in curve if x['decisions']==n)
    prefix=f'tactical-next-{kind.replace("_","-")}-seed{seed}-{step}m-';extra=read(P/f'{prefix}{placement}-extra.json')
   pocket=read(P/f'{prefix}distant-pocket-6-retreat.json')['arms'];hall=read(P/f'{prefix}hallway-six-retreat.json')['arms'];forced=pocket[arm+'_force_route'];f=extra['frozen']['summary']['first_contact']
   d=dict(seed=seed,clear=final['sampled']['clear_rate'],hall=avg(hall[arm]['win'][16:20]),pocket=avg(pocket[arm]['win'][16:20]),forced=avg(forced['win'][16:20]),wait=sum(forced['pocket_wait_turns'][16:20])/sum(forced['pocket_contact_turns'][16:20]),heldout=extra['heldout']['aggregate']['clear'],frozen_wait=f['mean_wait'],rotation_wait_range=f['mean_rotation_wait_range'],training_seconds=final['train_seconds'],additional_train_seconds=final['train_seconds']-result['job'].get('source_train_seconds',0))
   counts=final.get('curriculum_counts')
   if counts:d.update(tactical_decision_fraction=counts[1]/sum(counts[:2]),tactical_episode_fraction=counts[3]/sum(counts[2:4]))
   seeds.append(d)
  row=dict(kind=kind,step=step,placement=placement,seeds=seeds,mean={k:avg(s[k] for s in seeds) for k in seeds[0] if k!='seed'});rows.append(row)
  print(kind,step,placement, {k:round(v*(1 if 'seconds' in k else 100),2) for k,v in row['mean'].items()})
(P/'tactical-next-comparison.json').write_text(json.dumps(rows,indent=2)+'\n')
