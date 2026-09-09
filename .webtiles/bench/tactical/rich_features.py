"""V2 selector inputs. No seed, RNG, turn, hidden entities or outcome features.

Raw observations keep all enemies and known cells. The linear adapter uses
eight deterministic nearest-enemy slots plus all-enemy aggregates, a visible
17x17 local map, gear/skills, and selected cross-features.
"""
import math
import json
from itertools import combinations
from goal_controllers import features as coarse_features, dist, paths, destinations

VERSION=2

def values(x): return list(x.values()) if isinstance(x,dict) else list(x or [])

def features(s):
    if s.get('rich_version')!=VERSION: raise ValueError('Rich observation v2 required; recollect old snapshots')
    f=coarse_features(s)
    def number(key,value,scale=1):
        if isinstance(value,(int,float)) and math.isfinite(value):
            f[key]=max(-10.,min(10.,value/scale));f[key+'/known']=1.
    def category(key,value):
        if isinstance(value,str) and value: f[key+'='+value.lower()]=1.
    p=s['player']
    for key,scale in {'xl':27,'ac':50,'ev':50,'sh':50,'strength':40,
        'intelligence':40,'dexterity':40,'mp':50,'max_mp':50,'willpower':200,
        'see_invisible':1,'flying':1}.items():number('player/'+key,p.get(key),scale)
    for key in ('species','class'):category('player/'+key,p.get(key))
    for key,v in p.items():
        if key.startswith('res_'):number('player/'+key,v,3)
    number('player/max_hp',s['max_hp'],200)
    for key,v in p['skills'].items():number('skill/'+key,v,27)
    for flag in ('confused','poisoned','on_fire','berserk','cooldown','safe'):
        number('status/'+flag,bool(s.get(flag)))
    for flag in ('held','mesmer','constrict','slow','corrod','petrif','teleport'):
        number('status/'+flag,flag in s.get('status','').lower())
    gear_counts={}
    for g in sorted(values(s['gear']),key=lambda g:json.dumps(
            {k:v for k,v in g.items() if k!='name'},sort_keys=True)):
        # Inventory letters and full item names (including inscriptions) are not features.
        kind=str(g.get('subtype') or g.get('class','unknown'))
        key='gear/'+str(g.get('equip_type','none'))+'/'+kind if g.get('equipped') else 'inventory/'+kind
        if g.get('equipped'):
            gear_counts[key]=gear_counts.get(key,0)+1
            key+=f'/{gear_counts[key]}'
        f[key+'/quantity']=f.get(key+'/quantity',0)+min(100,g.get('quantity',1))/20
        category(key+'/ego',g.get('ego'))
        if g.get('class')=='wand':number(key+'/charges',g.get('plus'),20)
        if g.get('equipped'):
            for k,scale in {'plus':10,'damage':30,'damage_rating':100,'accuracy':20,
                'delay':20,'ac':20,'encumbrance':30,'reach_range':8,'is_ranged':1,
                'is_shield':1,'is_melded':1}.items():number(key+'/'+k,g.get(k),scale)
            for k,v in (g.get('artprops') or {}).items():number(key+'/property/'+k,v,10)
    es=sorted(values(s['enemy_details']),key=lambda e:(dist((e['x'],e['y'])),e['x'],e['y'],str(e.get('type'))))
    for i,e in enumerate(es):
        d=dist((e['x'],e['y']));kind=str(e.get('type',e.get('name','unknown')))
        f['enemy_type_count/'+kind]=f.get('enemy_type_count/'+kind,0)+1/8
        for spell in values(e.get('spells')):
            f['enemy_spell_count/'+spell]=f.get('enemy_spell_count/'+spell,0)+1/8
        if i>=8:continue
        pre=f'enemy/{i}/'
        category(pre+'type',kind);category(pre+'speed',e.get('speed_description'))
        category(pre+'status',e.get('status'))
        for k,scale in {'x':8,'y':8,'threat':3,'damage_level':5,'ac':5,'ev':5,'wl':5,
            'range':8,'reach_range':8,'reachable':1,'is_unique':1,'is_stationary':1,
            'is_constricting_you':1}.items():number(pre+k,e.get(k),scale)
        for k in ('res_poison','res_fire','res_cold','res_draining','res_shock','res_corr'):
            number(pre+k,e.get(k),3)
        for spell in values(e.get('spells')):category(pre+'spell',spell)
        number(pre+'ranged_distance',float(e.get('range',1)>1)*d,8)
        number(pre+'hp_x_threat',s['hp']/s['max_hp']*e['threat'],3)
    number('arrangement/overflow',max(0,len(es)-8),8)
    pairs=list(combinations(es,2))
    number('arrangement/near_pairs',sum(dist((a['x']-b['x'],a['y']-b['y']))<=2 for a,b in pairs),28)
    number('arrangement/opposing_pairs',sum(a['x']*b['x']+a['y']*b['y']<0 for a,b in pairs),28)
    number('arrangement/ranged',sum(e.get('range',1)>1 for e in es),8)
    for c in values(s.get('known')):
        x,y=c['x'],c['y']
        if not c.get('visible') or max(abs(x),abs(y))>8:continue
        pre=f'cell/{x}/{y}/';f[pre+'visible']=1.
        category(pre+'terrain',c.get('feature'))
        for k in ('traversable','unsafe','occupied','invisible_monster','withheld'):
            number(pre+k,bool(c.get(k)))
        if c.get('cloud'):category(pre+'cloud',str(c['cloud']))
    retreat,choke=destinations(s);routes=paths(s,ignore_occupied=True)
    for kind,target in [('retreat',retreat),('choke',choke)]:
        if target and target[0] in routes:number(kind+'/path_length',len(routes[target[0]]),40)
    if not all(math.isfinite(v) for v in f.values()):raise ValueError('Non-finite features')
    return f
