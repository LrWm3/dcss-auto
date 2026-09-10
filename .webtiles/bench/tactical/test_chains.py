import copy
import unittest
import numpy as np

from action_env import ACTIONS, legal_mask
from benchmark_chains import ChainRecovery, check_boundary, choose


class ChainsTests(unittest.TestCase):
    def state(self):
        return dict(chain=dict(stage=1, total=3, native=dict(alive=1)),
                    monsters={'1':dict(x=1,y=0,threat=2)}, hp=40,max_hp=40,
                    can_berserk=True, known={}, cells={}, turn=10, floor='D:4')

    def test_real_cooldown_and_active_berserk_mask(self):
        for field in ('cooldown','berserk','confused'):
            s=self.state();s[field]=True
            self.assertFalse(legal_mask(s)[-1])
            self.assertNotEqual(choose(s,legal_mask(s),'every_wave',set()),ACTIONS.index('berserk'))

    def test_last_wave_saves_and_failed_ability_can_retry(self):
        s=self.state();mask=np.ones(len(ACTIONS),dtype=bool)
        self.assertNotEqual(choose(s,mask,'last_wave',set()),ACTIONS.index('berserk'))
        s['chain']['stage']=3
        self.assertEqual(choose(s,mask,'last_wave',set()),ACTIONS.index('berserk'))
        self.assertNotEqual(choose(s,mask,'last_wave',{3}),ACTIONS.index('berserk'))

    def test_cannot_recover_with_unseen_wave_survivor(self):
        s=self.state();s['monsters']={};s['chain']['stage']=3
        r=ChainRecovery()
        for _ in range(50):
            after=copy.deepcopy(s);after['turn']+=1
            self.assertFalse(r.observe(s,after));s=after
        self.assertEqual(r.quiet,0)

    def test_every_boundary_field_is_checked(self):
        before=dict(turn=10,hp=20,max_hp=40,mp=2,max_mp=3,x=1,y=2,
                    durations={'1':10},alive=0)
        after=dict(before,alive=1)
        check_boundary(dict(before=before,after=after))
        for key in ('turn','hp','max_hp','mp','max_mp','x','y','durations'):
            changed=copy.deepcopy(after)
            changed[key]={'1':0} if key=='durations' else changed[key]+1
            with self.assertRaises(ValueError):
                check_boundary(dict(before=before,after=changed))


if __name__=='__main__':unittest.main()
