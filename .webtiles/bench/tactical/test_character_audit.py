import copy
import json
from pathlib import Path
import tempfile
import unittest
from bench import HERE, sha
from character_audit import row_identity, trajectory
from rich_features import features
from run_goals import options
from test_rich_features import rich


class AuditTests(unittest.TestCase):
    def test_rejects_feature_and_seed_tampering(self):
        s = rich()
        family = dict(id='family', seed='123', split='train')
        variant = dict(id='family/control', recipe=dict(axis='none'))
        row = dict(case_id=variant['id'], family_id=family['id'], seed='123',
                   split_group='123', split='train', recipe=variant['recipe'],
                   feature_version=2, feature_source_sha256=sha(HERE/'rich_features.py'),
                   rich_bridge_sha256=sha(HERE/'rich_goal_bridge.lua'),
                   features=features(s), available=options(s))
        row_identity(row, family, variant, s)
        for key, value in [('seed', '456'), ('split', 'test'), ('feature_version', 1),
                           ('features', {}), ('available', [])]:
            bad = copy.deepcopy(row); bad[key] = value
            with self.assertRaises(ValueError):
                row_identity(bad, family, variant, s)

    def test_trace_checksum_and_continuity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'transitions.jsonl'
            s = rich(); t = copy.deepcopy(s); t['turn'] += 1
            path.write_text(json.dumps(dict(observation=s, next_observation=t))+'\n')
            self.assertEqual(trajectory(directory, sha(path)), [s, t])
            with self.assertRaises(ValueError):
                trajectory(directory, 'bad-digest')
            with path.open('a') as stream:
                stream.write(json.dumps(dict(observation=s, next_observation=t))+'\n')
            with self.assertRaises(ValueError):
                trajectory(directory)


if __name__ == '__main__':
    unittest.main()
