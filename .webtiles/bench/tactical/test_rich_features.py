import copy
import unittest
from test_goal_controllers import state
from rich_features import features
from rich_goals import select,fit
from bench import HERE,sha

def rich():
    s=state();s.update(rich_version=2,player={'xl':5,'ac':7,'skills':{'Axes':4}},
        gear={'1':{'equipped':True,'equip_type':'weapon','subtype':'hand axe','damage':7}},
        enemy_details={'1':dict(type='orc',x=2,y=0,threat=1,range=1,spells={}),
                       '2':dict(type='orc',x=3,y=0,threat=1,range=1,spells={})})
    return s

class RichTests(unittest.TestCase):
    def test_gear_skills_level_and_stats_distinguishable(self):
        a=rich()
        for change in (lambda s:s['player'].update(xl=8),lambda s:s['player'].update(ac=15),
          lambda s:s['player']['skills'].update(Axes=12),
          lambda s:s['gear']['1'].update(damage=18,subtype='battleaxe')):
            b=copy.deepcopy(a);change(b);self.assertNotEqual(features(a),features(b))
    def test_enemy_identity_arrangement_spells_and_health(self):
        a=rich()
        for change in ({'x':-3},{'type':'orc priest'},{'spells':{'1':'Smiting'}},{'damage_level':3}):
            b=copy.deepcopy(a);b['enemy_details']['2'].update(change)
            self.assertNotEqual(features(a),features(b))
    def test_visible_clouds_but_not_hidden_cells(self):
        a=rich();b=copy.deepcopy(a);b['known']['1:0']['cloud']='steam'
        self.assertNotEqual(features(a),features(b))
        a['known']['1:0']['visible']=False;b['known']['1:0']['visible']=False
        self.assertEqual(features(a),features(b))
    def test_entity_order_and_metadata_invariance(self):
        a=rich();b=copy.deepcopy(a);b['enemy_details']=dict(reversed(list(b['enemy_details'].items())))
        b.update(seed='different',augmentation={'rng_draws':999},messages={'1':'secret'},turn=999)
        self.assertEqual(features(a),features(b))
    def test_old_states_models_and_unaudited_labels_rejected(self):
        with self.assertRaises(ValueError):features(state())
        with self.assertRaises(ValueError):select({},rich())
        with self.assertRaises(ValueError):fit([{'split':'train'}])
    def test_duplicate_equipment_order_invariance(self):
        a=rich();a['gear']['2']=dict(a['gear']['1'],damage=12)
        b=copy.deepcopy(a);b['gear']=dict(reversed(list(b['gear'].items())))
        self.assertEqual(features(a),features(b))
    def test_stale_feature_rows_rejected(self):
        with self.assertRaises(ValueError):fit([dict(feature_version=2,split='train',
            evidence_verified=True,outcome='death',feature_source_sha256='old')])
    def test_new_feature_can_change_actual_selector_choice(self):
        a=rich();b=copy.deepcopy(a);b['player']['xl']=20
        model=dict(feature_version=2,feature_source_sha256=sha(HERE/'rich_features.py'),
            rich_bridge_sha256=sha(HERE/'rich_goal_bridge.lua'),
            weights={'defend:0':{'bias':.3},'pursue:0':{'player/xl':1}})
        self.assertEqual(select(model,a),'defend:0')
        self.assertEqual(select(model,b),'pursue:0')
    def test_training_cannot_read_heldout_rows(self):
        with self.assertRaises(ValueError):fit([dict(feature_version=2,split='test',
            evidence_verified=True,outcome='death')])

if __name__=='__main__':unittest.main()
