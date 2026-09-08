import unittest
from tactical_options import Tactic
from test_training import state


class TacticsTests(unittest.TestCase):
    def test_hold_does_not_approach(self):
        s=state();s['monsters']['1']['x']=3
        self.assertEqual(Tactic('hold')(s),'wait')
        self.assertEqual(Tactic('hold')(state()),'melee')

    def test_rage_commit_does_not_walk_or_wait_adjacent(self):
        tactic=Tactic('rage_hold')
        self.assertEqual(tactic(state()),'berserk')
        self.assertEqual(tactic(state(berserk=True)),'melee')
        self.assertEqual(tactic(state(cooldown=True)),'melee')

    def test_retreat_uses_open_cell_away_from_enemy(self):
        self.assertEqual(Tactic('retreat')(state()),'w')
        s=state();s['cells']['-1:0']['cloud']='steam'
        self.assertEqual(Tactic('retreat')(s),'melee')

    def test_blocked_retreat_can_commit_to_fight(self):
        s=state(cells={})
        t=Tactic('retreat_fight')
        self.assertEqual(t(s),'berserk')
        self.assertEqual(t(state(berserk=True)),'melee')

    def test_status_and_recovery_delegate_safely(self):
        for policy in ('hold','rage_hold','retreat','retreat_fight'):
            self.assertEqual(Tactic(policy)(state(poisoned=True)),'baseline')
            self.assertEqual(Tactic(policy)(state(monsters={},safe=True)),'wait')


if __name__=='__main__':unittest.main()
