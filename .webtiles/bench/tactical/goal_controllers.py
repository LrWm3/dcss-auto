"""Goal-based, bounded tactical options using only player-known geometry.

Berserk is an independent permission, checked at each adjacent fight; it never
changes the navigation goal. All options use the same observable endpoint.
"""
from collections import deque
import heapq
from experiment import DIRECTIONS
from train_encounters import enemies

GOALS=('withdraw','defend','pursue')
VECTORS={v:k for k,v in DIRECTIONS.items()}
def dist(a,b=(0,0)): return max(abs(a[0]-b[0]),abs(a[1]-b[1]))
def position(s): return (s['position']['x'],s['position']['y'])
def point(c): return (c['x'],c['y'])
def add(a,b): return (a[0]+b[0],a[1]+b[1])
def sub(a,b): return (a[0]-b[0],a[1]-b[1])
def terrain(c):
    f=c.get('feature','')
    return (c.get('traversable') and not any(c.get(k) for k in
        ('cloud','unsafe','excluded','mapped','invisible_monster')) and
        (f in ('floor','open_door') or f.startswith('stone_stairs_')))

def geometry(s):
    return {point(c):c for c in s.get('known',{}).values()}

def paths(s, limit=100, ignore_occupied=False, frontier=True):
    """Dijkstra favors avoiding hostile adjacency, without assuming unseen safety."""
    cells=geometry(s); es=enemies(s); queue=[(0,0,(0,0))]
    cost={(0,0):0}; routes={(0,0):[]}
    while queue:
        score,length,p=heapq.heappop(queue)
        if score!=cost[p] or length>=limit: continue
        for action,d in DIRECTIONS.items():
            q=add(p,d); c=cells.get(q,{})
            if not terrain(c) or (not frontier and c.get('frontier')): continue
            if not ignore_occupied and c.get('occupied'): continue
            penalty=sum(8 if dist(q,point(e))<=1 else 0 for e in es)
            new=score+1+penalty
            if new<cost.get(q,float('inf')):
                cost[q]=new; routes[q]=routes[p]+[action]
                heapq.heappush(queue,(new,length+1,q))
    return routes

def degree(cells,p):
    return sum(bool(cells.get(add(p,d),{}).get('traversable')) for d in DIRECTIONS.values())

def destinations(s):
    routes=paths(s,ignore_occupied=True); cells=geometry(s); anchors=s.get('anchors',{})
    retreat=[]
    # Only a recorded entry upstairs certifies that the other side was visited.
    # A shaft with no such anchor masks upstairs, but need not mask a rest anchor.
    for priority,kind in enumerate(('stairs','rest','entry')):
        if kind not in anchors: continue
        p=point(anchors[kind]); c=cells.get(p,{})
        if p not in routes or not terrain(c): continue
        if kind=='stairs' and (s['floor']=='D:1' or not c.get('feature','').startswith('stone_stairs_up')):
            continue
        # An arbitrary entry point in the open is not itself a safety destination.
        if kind=='entry' and degree(cells,p)>4: continue
        retreat.append((priority,len(routes[p]),p,kind))
    chokepoints=[]
    for p,path in paths(s,limit=6,frontier=False).items():
        if not terrain(cells.get(p,{})): continue
        if not all(add(p,d) in cells for d in DIRECTIONS.values()): continue
        n=degree(cells,p)
        if n>4 or (n>3 and n>=degree(cells,(0,0))): continue
        # Do not set up among multiple already-adjacent threats.
        contacts=sum(dist(p,point(e))<=1 for e in enemies(s))
        chokepoints.append((contacts,n,len(path),p))
    return (min(retreat)[2:] if retreat else None,
            (min(chokepoints)[3],'choke') if chokepoints else None)

def available(s):
    retreat,choke=destinations(s)
    return [g for g,ok in [('withdraw',retreat),('defend',choke),('pursue',True)] if ok]

def clean(s):
    if s.get('terminal'): return False
    harmful=('poison','confus','liquid fire','on fire','slow','exhaust','corrod',
             'constrict','mesmer','held','petrif','rot','teleport','mark')
    return (s['hp']==s['max_hp'] and not enemies(s) and s.get('safe')
        and not any(s.get(k) for k in ('berserk','cooldown','confused','poisoned','on_fire','unseen'))
        and not any(k in s.get('status','').lower() for k in harmful)
        and not any(c.get('invisible_monster') for c in s.get('known',{}).values())
        and not geometry(s).get((0,0),{}).get('cloud'))

class Recovery:
    def __init__(self): self.quiet=0
    def observe(self,before,after):
        # Counting only actual one-turn boundaries prevents macro-wait overshoot.
        delta=after.get('turn',before['turn'])-before['turn']
        if clean(before) and clean(after) and before['floor']==after['floor'] and delta==1:
            self.quiet+=1
        else: self.quiet=0
        return self.quiet>=20

class Controller:
    def __init__(self,goal,berserk=False):
        if goal not in GOALS: raise ValueError(goal)
        self.requested=goal; self.goal=goal; self.berserk=berserk
        self.floor=None; self.target=None; self.kind=None
        self.events=[]; self.reason=''; self.idle=0; self.pursuit=0
        self.origin=None; self.peak=0; self.rage_attempt=None; self.emergency_turn=-100
        self.enemy_count=0
    def fight(self,s):
        if self.berserk and s.get('can_berserk') and not s.get('cooldown') and not s.get('berserk'):
            if self.rage_attempt is None or s['turn']-self.rage_attempt>10:
                self.rage_attempt=s['turn']; self.note(s,'independent berserk activation'); return 'berserk'
        return 'melee'
    def note(self,s,reason):
        self.reason=reason
        if not self.events or self.events[-1]['reason']!=reason:
            self.events.append(dict(turn=s['turn'],floor=s['floor'],reason=reason,goal=self.goal))
    def fallback(self,s,reason):
        self.note(s,reason)
        retreat,choke=destinations(s)
        if self.goal!='withdraw' and retreat:
            self.goal='withdraw'; self.target=add(position(s),retreat[0]); self.kind=retreat[1]
        else:
            self.goal='pursue'; self.target=None; self.kind=None
    def __call__(self,s):
        es=enemies(s); adjacent=[e for e in es if e.get('reachable') and dist(point(e))<=1]
        if self.floor!=s['floor']:
            transitioned=self.floor is not None
            self.floor=s['floor']; self.target=None; self.origin=position(s)
            if transitioned:
                self.goal='defend'; self.target=position(s); self.kind='arrival'
                self.note(s,'floor transition: fight followers, then recover')
            else:
                retreat,choke=destinations(s)
                chosen={'withdraw':retreat,'defend':choke,'pursue':None}[self.goal]
                if self.goal!='pursue' and chosen is None:
                    raise ValueError('Unavailable goal: '+self.goal)
                if chosen: self.target=add(position(s),chosen[0]); self.kind=chosen[1]
        status=s.get('status','').lower()
        hazard=any(s.get(k) for k in ('confused','poisoned','on_fire')) or any(
            k in status for k in ('mesmer','constrict','held','rooted','petrif','immotile'))
        emergency=s['hp']/s['max_hp']<.3 and s['turn']-self.emergency_turn>=5
        if hazard or geometry(s).get((0,0),{}).get('cloud') or emergency:
            self.emergency_turn=s['turn']
            self.note(s,'shared emergency/hazard response'); return 'safety'
        if not es:
            self.idle=0
            if not s.get('safe') or s.get('unseen'):
                self.note(s,'unseen threat: resolve without declaring recovery')
                if self.goal!='withdraw': self.fallback(s,'unseen threat: seek known safety')
                if self.goal!='withdraw': return 'safety'
            elif self.goal!='withdraw' or self.target is None:
                self.note(s,'heal and verify quiet, one turn at a time'); return 'wait'
        peak=max((e['threat'] for e in es),default=0)
        if self.pursuit and (peak>self.peak or len(es)>self.enemy_count):
            self.fallback(s,'new threats during pursuit: reassess')
        self.peak=max(self.peak,peak); self.enemy_count=len(es)
        # Do not rage merely because foes are visible: only actual close fighting.
        # Independent permission applies even to withdrawal blockers.
        if self.target is not None:
            relative=sub(self.target,position(s)); routes=paths(s)
            if relative==(0,0):
                if self.goal=='withdraw' and self.kind=='stairs':
                    self.note(s,'ascend recorded entry stairs'); return 'up'
                if adjacent: self.note(s,'fight at defensive destination'); return self.fight(s)
                if not es and s.get('safe'):
                    self.note(s,'recover at destination'); return 'wait'
                self.idle+=1
                if self.idle<=8:
                    self.note(s,'bounded lure at defensive destination'); return 'wait'
                self.fallback(s,'enemy refuses lure: abandon stationary hold')
            elif relative in routes and routes[relative]:
                # Withdrawal can maneuver past enemies instead of automatically Tab-attacking.
                self.note(s,'route to '+str(self.kind)); return routes[relative][0]
            elif adjacent:
                self.note(s,'fight escape-route blocker'); return self.fight(s)
            else: self.fallback(s,'route unavailable: reassess')
        if adjacent:
            self.note(s,'adjacent combat without chasing'); return self.fight(s)
        if not es:
            self.note(s,'unseen or recovery safety check'); return 'safety'
        routes=paths(s,limit=8,frontier=False)
        # Nearest reachable foe, tie-break on threat. Approach only an adjacent tile.
        targets=sorted((e for e in es if e.get('reachable')),
                       key=lambda e:(dist(point(e)),-e['threat'],e['x'],e['y']))
        for e in targets:
            choices=[(len(path),p,path) for p,path in routes.items() if path and dist(p,point(e))==1]
            if choices and self.pursuit<12 and dist(position(s),self.origin)<8:
                self.pursuit+=1; self.note(s,'bounded known-terrain pursuit'); return min(choices)[2][0]
        self.idle+=1
        if self.idle==9: self.fallback(s,'pursuit unavailable/exhausted: seek safety')
        self.note(s,'no safe approach: bounded unresolved wait'); return 'safety'

def features(s):
    retreat,choke=destinations(s); es=enemies(s); cells=geometry(s)
    return dict(bias=1.,hp=s['hp']/s['max_hp'],enemies=min(8,len(es))/8,
        red=min(4,sum(e['threat']>=3 for e in es))/4,
        adjacent=min(8,sum(dist(point(e))<=1 for e in es))/8,
        distance=min((dist(point(e)) for e in es),default=8)/8,
        withdraw=float(retreat is not None),defend=float(choke is not None),
        escape_distance=min(40,dist(retreat[0]))/40 if retreat else 1.,
        choke_distance=dist(choke[0])/8 if choke else 1.,
        openness=degree(cells,(0,0))/8,can_berserk=float(s.get('can_berserk',False)),
        cooldown=float(bool(s.get('cooldown'))),poison=float(bool(s.get('poisoned'))),
        unseen=float(bool(s.get('unseen') or not s.get('safe') and not es)),
        frontier=float(bool(cells.get((0,0),{}).get('frontier'))))
