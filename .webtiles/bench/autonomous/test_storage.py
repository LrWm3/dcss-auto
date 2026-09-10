import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import storage
from train_model import rows_from_replay


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "replay").mkdir()
        self.old_root = storage._root
        storage.configure(self.root)

    def tearDown(self):
        storage._root = self.old_root
        self.tmp.cleanup()

    def episode(self, name, steps=1):
        p = self.root / "replay" / (name + ".jsonl")
        row = {"type": "transition", "observation": {"schema": "crawl-general-v1"},
               "return": None}
        p.write_text((json.dumps(row) + "\n") * steps)
        storage.result_path(p).write_text(json.dumps({"steps": steps, "terminal": True, "score": 41}))
        return p

    def test_pause_hysteresis_and_live_status(self):
        checks = iter([19, 19, 20, 21, 22])
        sleeps = []
        def sleeping(seconds):
            sleeps.append(seconds)
            self.assertEqual(len(list((self.root / "storage_pauses").glob("*.json"))), 1)
        with patch.object(storage.shutil, "disk_usage", side_effect=lambda _: SimpleNamespace(free=next(checks)*storage.GIB)), \
             patch.object(storage.time, "sleep", side_effect=sleeping):
            storage.guard()
        self.assertEqual(sleeps, [5, 5])
        self.assertFalse(list((self.root / "storage_pauses").glob("*.json")))

    def test_compressed_replay_preserves_final_score(self):
        path = self.episode("a", 3)
        before = path.read_bytes()
        storage.compress(path)
        compressed = path.with_name(path.name + ".gz")
        with storage.open_text(compressed) as stream:
            self.assertEqual(stream.read().encode(), before)
        self.assertFalse(path.exists())
        self.assertEqual([r["return"] for r in rows_from_replay(self.root / "replay")], [41]*3)

    def test_new_worker_obeys_existing_pause_at_21_gib(self):
        storage._paused.set()
        readings = iter([21, 21, 21, 22])
        with patch.object(storage.shutil, "disk_usage", side_effect=lambda _: SimpleNamespace(free=next(readings)*storage.GIB)), \
             patch.object(storage.time, "sleep") as sleep:
            storage.guard()
        sleep.assert_called_once_with(5)
        self.assertFalse(storage._paused.is_set())

    def test_retention_only_completed_replay(self):
        self.episode("old", 2)
        self.episode("new", 2)
        partial = self.root / "replay" / "partial.jsonl"
        partial.write_text("failure evidence")
        keep = []
        for directory in ("state_archive", "champions", "failures", "metrics"):
            folder = self.root / directory
            folder.mkdir()
            file = folder / "preserve"
            file.write_text("preserve")
            keep.append(file)
        result = storage.maintain(self.root, max_rows=2)
        self.assertEqual(result["retained_replay_rows"], 2)
        self.assertEqual(len(result["removed"]), 1)
        self.assertTrue(partial.exists())
        self.assertTrue(all(p.read_text() == "preserve" for p in keep))
        self.assertTrue(storage.result_path(self.root / "replay" / "old.jsonl").exists())

    def test_byte_cap_can_evict_oversize_shard(self):
        self.episode("big")
        result = storage.maintain(self.root, max_bytes=1)
        self.assertEqual(result["retained_replay_bytes"], 0)

    def test_incomplete_replay_not_loaded(self):
        path = self.episode("partial")
        storage.result_path(path).unlink()
        self.assertEqual(rows_from_replay(path), [])

    def test_interrupted_transitions_are_not_counted_as_crashes(self):
        from train_crawl_agent import artifact_counts
        directory = self.root / "failures" / "invalid_states"
        directory.mkdir(parents=True)
        (directory / "interrupted.jsonl").write_text('{"type":"transition"}\n' * 3)
        (directory / "crash.jsonl").write_text('{"error":"test crash"}\n')
        counts = artifact_counts(self.root)
        self.assertEqual(counts["failure_rows"], 1)
        self.assertEqual(counts["interrupted_replay_rows"], 3)

    def test_cleanup_preserves_saves_and_nonredundant_events(self):
        work = self.root / "general-test"
        work.mkdir()
        for name in ("run.json", "events.jsonl", "terminal.txt", "checkpoint.cs"):
            (work / name).write_text("evidence")
        storage.finish_logs([work], redundant=False)
        self.assertTrue((work / "events.jsonl.gz").exists())
        self.assertTrue((work / "checkpoint.cs").exists())
        (work / "events.jsonl").write_text("duplicate")
        storage.finish_logs([work], redundant=True)
        self.assertFalse((work / "events.jsonl").exists())
        self.assertTrue((work / "terminal.txt.gz").exists())

    @unittest.skipUnless(os.environ.get("CRAWL_STORAGE_LIVE_TEST"), "opt-in real engine test")
    def test_live_game_does_not_advance_during_low_space_pause(self):
        from general_env import GeneralEnvironment
        env = GeneralEnvironment(self.root / "actor")
        try:
            before = env.launch()
            wait = next(i for i, a in enumerate(before["actions"]) if a["kind"] == "WAIT")
            free = [19 * storage.GIB]
            with patch.object(env.child, "send", wraps=env.child.send) as send:
                def release(_):
                    self.assertEqual(env.state["seq"], before["seq"])
                    send.assert_not_called()
                    self.assertTrue(storage.health(self.root)["paused"])
                    free[0] = 22 * storage.GIB
                with patch.object(storage.shutil, "disk_usage", side_effect=lambda _: SimpleNamespace(free=free[0])), \
                     patch.object(storage, "time", SimpleNamespace(time=storage.time.time, sleep=release)):
                    after = env.step(wait)
            self.assertEqual(after["seq"], before["seq"] + 1)
            self.assertFalse(storage.health(self.root)["paused"])
        finally:
            env.close()


if __name__ == "__main__":
    unittest.main()
