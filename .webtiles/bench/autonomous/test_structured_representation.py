import copy
import unittest
import torch
import structured_features as f
from structured_model import StructuredScorer
from observation_history import add_history


class StructuredRepresentationTests(unittest.TestCase):
    def test_explicit_health_boundary_and_missingness(self):
        self.assertEqual(f.health_features({'hp':19,'max_hp':19}),[1.,1.,0.,0.])
        injured=f.health_features({'hp':18,'max_hp':19})
        self.assertEqual(injured[:2],[1.,0.])
        self.assertGreater(injured[2],0)
        self.assertEqual(f.health_features({}),[0.,0.,0.,0.])

    def setUp(self):
        torch.set_num_threads(1)
        self.s = {'schema':'crawl-general-v1','branch':'D','level':'D:1','depth':1,
                  'player':{'hp':15,'max_hp':20,'x':10,'y':10},
                  'monsters':[], 'inventory':[], 'history':[],
                  'known':{'0:0':{'x':0,'y':0,'feature':'floor','traversable':True},
                           '1:0':{'x':1,'y':0,'feature':'floor','traversable':True}}}

    def grid(self, state):
        return torch.tensor(f.state_features(state)[f.GLOBAL_DIM:f.GLOBAL_DIM+f.GRID_DIM]).reshape(f.SIDE,f.SIDE,-1)

    def test_branch_actual_value_and_unknown_kind(self):
        other = copy.deepcopy(self.s); other['branch']='Lair'; other['level']='Lair:1'
        self.assertNotEqual(f.state_features(self.s), f.state_features(other))
        action=f.action_features(self.s, {'kind':'NEW_KIND'})
        self.assertEqual(action[len(f.KINDS)],1)
        self.assertEqual(action[len(f.KINDS)+1],0)

    def test_cell_locality_and_ninth_monster(self):
        other=copy.deepcopy(self.s)
        other['cells']=[{'x':1,'y':0,'visible':True,'cloud':'steam'}]
        changed=(self.grid(other)!=self.grid(self.s)).any(-1).nonzero().tolist()
        self.assertEqual(changed,[[8,9]])
        other['monsters']=[{'x':i-4,'y':2,'threat':1} for i in range(9)]
        original=self.grid(other)
        other['monsters'][-1]['threat']=3
        self.assertEqual((original!=self.grid(other)).any(-1).nonzero().tolist(),[[10,12]])

    def test_monster_order_does_not_change_state(self):
        self.s['monsters']=[{'x':1,'y':0,'name':'orc'},{'x':-2,'y':1,'name':'Sigmund'}]
        original=f.state_features(self.s)
        self.s['monsters'].reverse()
        self.assertEqual(original,f.state_features(self.s))

    def test_item_effects_target_binding_and_missingness(self):
        self.s['inventory']=[{'slot':0,'name':'potion of curing','class':'potion','identified':True},
                             {'slot':1,'name':'potion of haste','class':'potion','identified':True}]
        self.assertNotEqual(f.action_features(self.s,{'kind':'QUAFF','slot':0}),
                            f.action_features(self.s,{'kind':'QUAFF','slot':1}))
        self.s['monsters']=[{'x':0,'y':0,'threat':3}]
        a=f.action_features(self.s,{'kind':'WAIT'})
        self.s['monsters']=[]
        self.assertEqual(a,f.action_features(self.s,{'kind':'WAIT'}))
        self.assertNotEqual(f.monster_features({'x':1}),f.monster_features({'x':1,'ac':0}))
        self.assertEqual(f.item_features({'name':'pink potion','identified':False,'subtype':'haste'}),
                         f.item_features({'name':'pink potion','identified':False,'subtype':'poison'}))

    def test_history_reframes_invisible_enemy_and_marks_failure(self):
        self.s['monsters']=[{'name':'Sigmund','x':3,'y':0}]
        after=copy.deepcopy(self.s); after['player']['x']=11; after['monsters']=[]
        after['last_action_result']={'dispatch_accepted':False}
        after=add_history(self.s,{'kind':'MOVE','dx':1,'dy':0},after)
        self.assertEqual(after['history'][-1]['last_seen_enemies'][0]['x'],2)
        self.assertTrue(after['history'][-1]['failed'])
        self.assertEqual(float(self.grid(after)[8,10,-1]),1)
        new_floor={**after,'level':'D:2'}
        self.assertEqual(add_history(after,{'kind':'TAKE_STAIRS_DOWN'},new_floor)['history'][-1]['last_seen_enemies'],[])

    def test_model_gradients_reach_geometry_items_and_actions(self):
        self.s['inventory']=[{'slot':0,'name':'potion of curing','identified':True}]
        state=torch.tensor(f.state_features(self.s)).unsqueeze(0)
        self.assertEqual(state.shape[1],f.STATE_DIM)
        actions=torch.tensor([f.action_features(self.s,a) for a in
                              [{'kind':'WAIT'},{'kind':'MOVE','dx':1,'dy':0}]])
        self.assertEqual(actions.shape[1],f.ACTION_DIM)
        net=StructuredScorer(32)
        result=net((state,actions))
        result.sum().backward()
        for layer in (net.spatial[0],net.items[0],net.globals[0],net.head[0]):
            self.assertGreater(float(layer.weight.grad.abs().sum()),0)
        torch.testing.assert_close(result,net(torch.cat((state.expand(2,-1),actions),1)))

    def test_unavailable_position_is_inferred_only_when_unambiguous(self):
        from observation_history import observed_displacement
        self.s['player'].pop('x'); self.s['player'].pop('y')
        self.s['known']={str(i)+':0':{'x':i,'y':0,'feature':'wall' if i==0 else 'floor'} for i in range(6)}
        after=copy.deepcopy(self.s)
        after['known']={str(i-1)+':0':{**c,'x':i-1} for i,c in enumerate(self.s['known'].values())}
        self.assertEqual(observed_displacement(self.s,{'kind':'MOVE','dx':1,'dy':0},after),(1,0))
        self.s['known']={}; after['known']={}
        self.assertIsNone(observed_displacement(self.s,{'kind':'MOVE','dx':1,'dy':0},after))


if __name__=='__main__':
    unittest.main()
