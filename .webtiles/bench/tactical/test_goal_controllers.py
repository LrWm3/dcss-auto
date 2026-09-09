import copy
import unittest
from goal_controllers import Controller,Recovery,available,paths,clean

def state():
    known={}
    for x in range(-6,7):
        for y in range(-3,4):
            floor=y==0 or (abs(x)<2 and abs(y)<2)
            known[f'{x}:{y}']=dict(x=x,y=y,feature='floor' if floor else 'rock_wall',
                traversable=floor,visible=True)
    known['-5:0']['feature']='stone_stairs_up_i'
    return dict(hp=40,max_hp=40,turn=100,floor='D:3',position=dict(x=0,y=0),
        known=known,cells=known,anchors=dict(stairs=dict(x=-5,y=0)),
        monsters={},safe=True,can_berserk=True,status='')

def enemy(s,x=2,y=0):
    s['monsters']={'1':dict(name='orc',x=x,y=y,threat=2,reachable=True)}
    s['known'][f'{x}:{y}']['occupied']=True; s['safe']=False
    return s

class GoalsTest(unittest.TestCase):
    def test_shaft_masks_upstairs_not_rest(self):
        s=state();s['anchors']={}
        self.assertNotIn('withdraw',available(s))
        s['anchors']['rest']=dict(x=-3,y=0)
        self.assertIn('withdraw',available(s))
    def test_no_d1_exit(self):
        s=state();s['floor']='D:1'
        self.assertNotIn('withdraw',available(s))
    def test_withdraw_routes_away_without_raging(self):
        s=enemy(state(),1)
        self.assertIn(Controller('withdraw',True)(s),('w','nw','sw'))
    def test_blocker_fight_independent_rage(self):
        s=enemy(state(),-1)
        for k in ('-1:-1','-1:1'): s['known'][k]['traversable']=False
        self.assertEqual(Controller('withdraw',True)(s),'berserk')
        self.assertEqual(Controller('withdraw',False)(s),'melee')
    def test_ascend_not_success(self):
        s=state();s['anchors']['stairs']=dict(x=0,y=0)
        s['known']['0:0']['feature']='stone_stairs_up_i'
        c=Controller('withdraw');self.assertEqual(c(s),'up')
        t=copy.deepcopy(s);t['floor']='D:2';t['turn']+=1
        self.assertFalse(Recovery().observe(s,t));self.assertEqual(c(t),'wait')
        enemy(t,1);self.assertEqual(c(t),'melee')
    def test_rage_does_not_commit_withdraw(self):
        s=state();s['berserk']=True
        self.assertIn(Controller('withdraw',True)(s),('w','nw','sw'))
    def test_frontier_no_pursuit(self):
        s=state();s['known']['-2:0']['frontier']=True
        self.assertNotIn((-3,0),paths(s,frontier=False))
    def test_cloud_no_route(self):
        s=state();s['known']['-2:0']['cloud']='steam'
        self.assertNotIn('withdraw',available(s))
    def test_quiet_twenty_actual_turns(self):
        s=state();r=Recovery()
        for i in range(20):
            t=copy.deepcopy(s);t['turn']+=1
            self.assertEqual(r.observe(s,t),i==19);s=t
    def test_damage_enemy_unseen_reset(self):
        for field,value in [('hp',39),('unseen',True),('berserk',True),('cooldown',True)]:
            s=state();r=Recovery();r.quiet=19;t=copy.deepcopy(s);t['turn']+=1;t[field]=value
            self.assertFalse(r.observe(s,t));self.assertEqual(r.quiet,0)
    def test_macro_wait_not_proof(self):
        s=state();t=copy.deepcopy(s);t['turn']+=100
        self.assertFalse(Recovery().observe(s,t))
    def test_ranged_hold_is_bounded(self):
        s=enemy(state(),5);c=Controller('defend');c.floor=s['floor']
        c.target=(0,0);c.origin=(0,0);c.kind='choke'
        for _ in range(10): c(s);s['turn']+=1
        self.assertNotEqual(c.goal,'defend')
    def test_unavailable_goal_rejected(self):
        s=state();s['anchors']={}
        with self.assertRaises(ValueError): Controller('withdraw')(s)
    def test_reach_enemy_interrupts_hold(self):
        s=enemy(state(),2);c=Controller('defend');c.floor=s['floor']
        c.target=(0,0);c.origin=(0,0)
        self.assertIn(c(s),('w','nw','sw'));self.assertEqual(c.goal,'withdraw')
    def test_damage_interrupts_distant_lure(self):
        s=enemy(state(),5);c=Controller('defend');c.floor=s['floor']
        c.target=(0,0);c.origin=(0,0)
        self.assertEqual(c(s),'wait');s['hp']-=2;s['turn']+=1
        self.assertIn(c(s),('w','nw','sw'))
    def test_lure_fallback_moves_to_stairs_same_decision(self):
        s=enemy(state(),5);c=Controller('defend');c.floor=s['floor']
        c.target=(0,0);c.origin=(0,0);c.idle=8
        self.assertIn(c(s),('w','nw','sw'));self.assertEqual(c.pursuit,0)
    def test_mesmerised_approach_and_no_forbidden_move(self):
        s=enemy(state(),3);s['status']='mesmerised'
        s['known']['1:0']['withheld']=True
        self.assertIn(Controller('withdraw')(s),('ne','se'))
    def test_mesmerised_melee_preserves_berserk_permission(self):
        s=enemy(state(),1);s['status']='mesmerised'
        self.assertEqual(Controller('pursue',False)(s),'melee')
        self.assertEqual(Controller('pursue',True)(s),'berserk')
    def test_withdraw_not_reversed_by_old_pursuit(self):
        s=enemy(state(),3);c=Controller('withdraw');c(s)
        c.pursuit=4;c.peak=0;c.enemy_count=0
        self.assertIn(c(s),('w','nw','sw'));self.assertEqual(c.goal,'withdraw')

if __name__=='__main__': unittest.main()
