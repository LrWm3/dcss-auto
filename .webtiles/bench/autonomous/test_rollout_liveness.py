import copy
import unittest
from rollout_liveness import ActivityTracker


class LivenessTests(unittest.TestCase):
    def state(self,hp=19,x=0):
        return {'level':'D:1','safe':True,'player':{'hp':hp,'max_hp':19,'x':x,'y':0},
                'turn':0,'monsters':[],'known':{},'score':0,'inventory':[]}

    def test_brief_full_health_wait_then_movement_allowed(self):
        s=self.state();tracker=ActivityTracker(s,idle_limit=8)
        for _ in range(7):self.assertFalse(tracker.record(s,{'kind':'WAIT'},s))
        moved=self.state(x=1)
        self.assertFalse(tracker.record(s,{'kind':'MOVE','dx':1,'dy':0},moved))
        self.assertEqual(tracker.events['new_position'],1)

    def test_reposition_while_injured_allowed(self):
        s=self.state(hp=5);tracker=ActivityTracker(s,idle_limit=4)
        for x in range(1,8):
            after=self.state(hp=5,x=x)
            self.assertFalse(tracker.record(s,{'kind':'MOVE','dx':1,'dy':0},after));s=after

    def test_healing_then_short_wait_allowed(self):
        s=self.state(hp=5);tracker=ActivityTracker(s,idle_limit=4)
        for hp in range(6,20):
            after=self.state(hp=hp)
            self.assertFalse(tracker.record(s,{'kind':'WAIT'},after));s=after
        for _ in range(3):self.assertFalse(tracker.record(s,{'kind':'WAIT'},s))
        self.assertTrue(tracker.record(s,{'kind':'WAIT'},s))

    def test_persistent_wait_flags_stall(self):
        s=self.state();tracker=ActivityTracker(s,idle_limit=4)
        for _ in range(3):self.assertFalse(tracker.record(s,{'kind':'WAIT'},s))
        self.assertTrue(tracker.record(s,{'kind':'WAIT'},s))

    def test_injury_and_passing_turns_are_not_progress(self):
        s=self.state();tracker=ActivityTracker(s,idle_limit=4)
        for i in range(4):
            after=self.state(hp=18-i);after['turn']=i+1
            stalled=tracker.record(s,{'kind':'WAIT'},after);s=after
        self.assertTrue(stalled)

    def test_threat_time_is_not_counted_as_safe_inactivity(self):
        s=self.state();s['safe']=False;s['monsters']=[{'name':'orc'}]
        tracker=ActivityTracker(s,idle_limit=4)
        for _ in range(8):self.assertFalse(tracker.record(s,{'kind':'WAIT'},s))
        after=self.state()
        self.assertFalse(tracker.record(s,{'kind':'WAIT'},after))

    def test_repeated_backtracking_does_not_reset_forever(self):
        s=self.state();tracker=ActivityTracker(s,idle_limit=4)
        flags=[]
        for i in range(7):
            after=self.state(x=(i+1)%2)
            flags.append(tracker.record(s,{'kind':'MOVE'},after));s=after
        self.assertTrue(flags[-1])

if __name__=='__main__':unittest.main()
