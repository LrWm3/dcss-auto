import copy
import unittest
from character_dataset import validate,preflight,unchanged_world,intent
from test_rich_features import rich

class CharacterTests(unittest.TestCase):
    def test_allowlist_and_bounds(self):
        for axis,name,v in [('gear','war_axe',3),('attribute','str',-4),('resistance','fire',1),('skill','Axes',3),('xl','xl',2)]:
            validate(dict(id='test',axis=axis,name=name,value=v))
        for axis,name,v in [('gear','executioners_axe',3),('attribute','str',99),('resistance','fire',-1),('skill','Axes',0),('xl','xl',True)]:
            with self.assertRaises(ValueError):validate(dict(id='test',axis=axis,name=name,value=v))
    def test_preflight_rejects_capped_and_invalid(self):
        s=rich();s['player'].update(xl=1,res_poison=1)
        for axis,name,v in [('xl','xl',-2),('resistance','poison',1)]:
            with self.assertRaises(ValueError):preflight(s,dict(axis=axis,name=name,value=v))
    def test_map_or_enemy_changes_rejected(self):
        s=rich()
        for e in s['enemy_details'].values():e.update(name='orc',damage_level=0)
        unchanged_world(s,copy.deepcopy(s))
        t=copy.deepcopy(s);t['enemy_details']['1']['x']=5
        with self.assertRaises(AssertionError):unchanged_world(s,t)
        t=copy.deepcopy(s);t['known']['0:0']['cloud']='steam'
        with self.assertRaises(AssertionError):unchanged_world(s,t)
    def test_skill_intent_requires_expected_value(self):
        s=rich()
        for e in s['enemy_details'].values():e.update(name='orc',damage_level=0)
        t=copy.deepcopy(s);t['player']['skills']['Axes']=7
        intent(s,t,dict(axis='skill',name='Axes',value=3))
        t['player']['skills']['Axes']=6
        with self.assertRaises(AssertionError):intent(s,t,dict(axis='skill',name='Axes',value=3))

if __name__=='__main__':unittest.main()
