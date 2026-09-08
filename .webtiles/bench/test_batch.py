"""Isolated runner tests: no real tmux sessions or benchmark rows modified."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import batch


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bench = self.root / '.webtiles/bench'
        self.state = self.bench / 'batches'
        self.state.mkdir(parents=True)
        self.game = self.root / 'crawl-0.35/crawl-ref/source'
        (self.game / 'morgue').mkdir(parents=True)
        (self.game / 'saves').mkdir()
        (self.game / 'crawl-webtiles').write_bytes(b'engine')
        self.rc = b'AUTOCrawl_TACTICS = {\n  berserk_hp = 55, crowd_berserk = true,\n}\n'
        (self.root / 'bot.rc').write_bytes(self.rc)
        (self.bench / 'runs.jsonl').write_text('')
        self.cfg = dict(version='test-v1', rc='bot.rc', stale_seconds=1,
                        sessions=[dict(session='test1', character='Test1', seed=batch.runner.SEEDS[0])])
        for obj, key, value in ((batch, 'ROOT', self.root), (batch, 'BENCH', self.bench),
                                (batch, 'STATE', self.state), (batch.runner, 'ROOT', self.bench)):
            p = patch.object(obj, key, value)
            p.start()
            self.addCleanup(p.stop)

    def launch(self):
        with patch.object(batch, 'panes', return_value=[]), patch.object(batch, 'command', return_value='%1'):
            batch.start(self.cfg, False)

    def test_snapshot_and_duplicate_start(self):
        self.launch()
        (self.root / 'bot.rc').write_bytes(b'changed')
        self.assertEqual((self.state / 'test-v1/tested.rc').read_bytes(), self.rc)
        with self.assertRaises(ValueError):
            batch.start(self.cfg, False)

    def test_foreign_session_refused(self):
        with patch.object(batch, 'panes', return_value=['%99']):
            with self.assertRaises(ValueError):
                batch.start(self.cfg, False)
        self.assertFalse((self.state / 'test-v1').exists())

    def test_policy_overrides(self):
        changed = batch.configured_rc(self.rc, dict(berserk_hp=0, crowd_berserk=False))
        self.assertIn(b'berserk_hp = 0', changed)
        self.assertIn(b'crowd_berserk = false', changed)
        for overrides in ({'unknown': 1}, {'crowd_berserk': 1}, {'berserk_hp': -1}):
            with self.assertRaises(ValueError):
                batch.configured_rc(self.rc, overrides)

    def test_death_collection_idempotent(self):
        self.launch()
        dump = self.game / 'morgue/morgue-Test1-20260907.txt'
        dump.write_text(f"Game seed: {batch.runner.SEEDS[0]} (custom seed)\n"
                        'Test1 the Fighter Turns: 532\nXL: 3\n 532 | D:2 | You die...\n')
        self.assertEqual(batch.collect('test-v1')['sessions'][0]['status'], 'death')
        batch.collect('test-v1')
        self.assertEqual(len((self.bench / 'runs.jsonl').read_text().splitlines()), 1)

    def test_stall_not_recorded_as_death(self):
        self.launch()
        with patch.object(batch, 'panes', return_value=['%1']), patch.object(batch, 'command', return_value='unchanged'):
            batch.collect('test-v1')
            with patch.object(batch.time, 'time', return_value=10**12):
                cfg = batch.collect('test-v1')
        self.assertEqual(cfg['sessions'][0]['status'], 'suspected_stall')
        self.assertEqual((self.bench / 'runs.jsonl').read_text(), '')

    def test_wrong_seed_dump_ignored(self):
        p = self.root / 'dump.txt'
        p.write_text('Game seed: 123 (custom seed)\nTest1 the Fighter Turns: 5\nYou die...')
        self.assertFalse(batch.terminal_dump(p, self.cfg['sessions'][0]))

    def test_numeric_seed_rejected(self):
        self.cfg['sessions'][0]['seed'] = int(batch.runner.SEEDS[0])
        p = self.root / 'config.json'
        p.write_text(json.dumps(self.cfg))
        with self.assertRaises(ValueError):
            batch.config(p)

    def test_completion_is_flag_not_unverified_benchmark_clear(self):
        self.launch()
        with patch.object(batch, 'panes', return_value=['%1']), patch.object(batch, 'command', return_value='ROUTE COMPLETE: Zot route explored'):
            self.assertEqual(batch.collect('test-v1')['sessions'][0]['status'], 'completion_reported')
        self.assertEqual((self.bench / 'runs.jsonl').read_text(), '')


if __name__ == '__main__':
    with contextlib.redirect_stdout(io.StringIO()):
        unittest.main()
