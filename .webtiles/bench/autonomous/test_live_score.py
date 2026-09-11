import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent))
from score_result import has_episode_score
from selection import confirmation_decision, screen_decision, ensure_protocol, PROTOCOL
from evaluate import comparison
from train_model import rows_from_replay


class LiveScoreTests(unittest.TestCase):
    def test_protocol_migration_preserves_old_declaration(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);path=root/'evaluations/selection_protocol.json'
            path.parent.mkdir()
            old={**PROTOCOL,'version':'screen-confirm-audit-v1'}
            path.write_text(json.dumps(old))
            self.assertEqual(ensure_protocol(root),PROTOCOL)
            self.assertEqual(json.loads(path.with_name('selection_protocol.v1.json').read_text()),old)

    def test_only_official_completed_episode_scores_are_accepted(self):
        self.assertTrue(has_episode_score({"truncated":True,"score_status":"cutoff_official","score":0}))
        for row in ({"score":-1,"truncated":True},
                    {"score":50,"score_status":"live_official"},
                    {"score":None,"truncated":True},
                    {"score":5,"terminal":True,"error":"crash"}):
            self.assertFalse(has_episode_score(row))

    def test_cutoffs_count_in_screen_confirmation_and_mean(self):
        a=[{"seed":str(i),"terminal":True,"score":10} for i in range(30)]
        b=[{"seed":str(i),"terminal":False,"truncated":True,
            "score_status":"cutoff_official","score":20,
            "truncation_reason":"floor_decision_limit"} for i in range(30)]
        self.assertTrue(confirmation_decision(a,b)["promote"])
        self.assertEqual(comparison(b)["mean_score"],20)
        self.assertEqual(screen_decision({"results":a},{"results":b})["state"],"awaiting_confirmation")

    def test_cutoff_score_becomes_episode_return_not_live_shaping(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/"episode.jsonl"
            p.write_text(json.dumps({"type":"transition","observation":{
                "schema":"crawl-general-v1","score":5},"return":None})+'\n')
            p.with_suffix('.result.json').write_text(json.dumps({
                "truncated":True,"score_status":"cutoff_official","score":40}))
            self.assertEqual(rows_from_replay(p)[0]["return"],40)

    @unittest.skipUnless(os.environ.get("CRAWL_STORAGE_LIVE_TEST"),"real engine opt-in")
    def test_live_cutoff_matches_official_quit_without_advancing_turn(self):
        from collect import run_episode
        from extract_cutoff_scores import extract
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            result=run_episode(root/'game','1760771545328102746',100,
                               snapshot=False,total_steps=100)
            self.assertTrue(result['truncated'])
            self.assertEqual(result['score_status'],'cutoff_official')
            p=root/'result.json';p.write_text(json.dumps(result))
            recovered=extract(p,root/'recovered')
            self.assertEqual(result['score'],recovered['score'])
            self.assertEqual(recovered['turns_advanced'],0)


if __name__ == '__main__':
    unittest.main()
