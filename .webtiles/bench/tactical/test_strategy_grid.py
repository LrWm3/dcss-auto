import unittest
from augmentation_dataset import classify
from augment_encounters import POLICIES
from probe_rng_strategies import summary, TARGETS


class StrategyGridTests(unittest.TestCase):
    def test_unknown_matrix_does_not_count_as_all_dead(self):
        rows=[dict(option=o,outcome='death',evidence_verified=True) for o in POLICIES]
        first=dict(family_id=TARGETS[0],offset=1,status='complete',rows=rows,label=classify(rows))
        partial=[dict(r) for r in rows]
        partial[0].update(outcome='unresolved_stall',evidence_verified=False)
        second=dict(family_id=TARGETS[0],offset=2,status='complete',rows=partial,label=classify(partial))
        report=summary([first,second])[TARGETS[0]]
        self.assertEqual(report['complete_matrices'],1)
        self.assertEqual(report['all_available_strategies_die'],[1])
        self.assertEqual(report['any_strategy_wins'],0)


if __name__=='__main__':unittest.main()
