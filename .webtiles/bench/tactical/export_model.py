"""Export a fitted state/action value table as a guarded experimental RC."""
import argparse
import ast
import json
from pathlib import Path

from bench import RC,HERE


def lua_key(key):
    values=ast.literal_eval(key)
    if not isinstance(values,tuple) or len(values)!=6:raise ValueError('Bad model key')
    return '|'.join(str(v).lower() if isinstance(v,bool) else str(v) for v in values)


def export(model, output):
    values=json.loads(model.read_text())
    lines=['local MODEL_Q={']
    for key,scores in sorted(values.items()):
        if any(a not in ('wait','tab','berserk','retreat') for a in scores):raise ValueError('Unknown option')
        fields=','.join('['+json.dumps(a)+']='+repr(float(v)) for a,v in sorted(scores.items()))
        lines.append('['+json.dumps(lua_key(key))+']={'+fields+'},')
    lines.append('}')
    source=RC.read_text()
    anchor='  if debug_encounter_pause(scan) then return end\n'
    assert source.count(anchor)==1
    source=source.replace(anchor,anchor+'  if ml_encounter_action(scan) then return end\n')
    at=source.rfind('>')
    with output.open('x') as f:
        f.write(source[:at]+'\n'+'\n'.join(lines)+'\n'+(HERE/'model_hook.lua').read_text()+'\n>\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('model',type=Path);p.add_argument('output',type=Path)
    args=p.parse_args();export(args.model,args.output)
