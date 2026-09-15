"""Report ordinary and pressure outcomes without pooling the task distributions."""
import json,pathlib,sys

def report(root):
 root=pathlib.Path(root);rows=[]
 for p in sorted(root.glob('runs/*/curve.json')):
  curve=json.loads(p.read_text());last=curve[-1]
  groups=json.loads((p.parent/'training-groups.json').read_text())['groups']
  total=sum(g['decisions'] for g in groups.values())
  rows.append(dict(job=p.parent.name,decisions=last['decisions'],train_seconds=last['train_seconds'],
       ordinary_clear=last['sampled']['clear_rate'],pressure_train_clear=last['pressure_train']['clear_rate'],
       pressure_heldout_clear=last['pressure_heldout']['clear_rate'],
       pressure_heldout_ogre_death=last['pressure_heldout']['ogre_death_rate'],
       pressure_heldout_clear_ogre_alive=last['pressure_heldout']['clear_with_all_ogres_alive_rate'],
       pressure_decision_fraction=groups['ogre_pressure']['decisions']/total if total else 0,
       training_groups=groups))
 (root/'comparison.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(rows,indent=2))
if __name__=='__main__':report(sys.argv[1])
