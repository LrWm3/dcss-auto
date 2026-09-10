import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
import selection
from data_split import assert_training_seed, held_out_seed
from train_model import rows_from_replay
from collect import run_episode


def games(n, score):
    return [{"seed":str(i), "score":score, "terminal":True} for i in range(n)]


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        (self.root/"champions").mkdir()
        self.champion=self.root/"champions/V0.pt"
        self.candidate=self.root/"candidate.pt"
        self.champion.write_bytes(b"champion")
        self.candidate.write_bytes(b"candidate")
        self.config={"decisions_per_floor":2000,"total_decisions":100000,"seeds":["1"]}
        self.identity=patch.object(selection,"environment_identity",return_value={"test":"environment"})
        self.identity.start()

    def tearDown(self):
        self.identity.stop()
        self.temp.cleanup()

    def batch(self,label="candidate-1",kind="confirmation"):
        return selection.prepare_batch(self.root,label,self.champion,self.candidate,self.config,kind)

    def test_screen_is_not_promotion(self):
        a={"results":games(5,10)}; b={"results":games(5,20)}
        result=selection.screen_decision(a,b)
        self.assertEqual(result["state"],"awaiting_confirmation")
        self.assertFalse(result["promote"])
        self.assertEqual(selection.screen_decision(b,a)["state"],"screen_failed")
        b["results"][0]["error"]="crash"
        self.assertEqual(selection.screen_decision(a,b)["category"],"broken")

    def test_training_restart_resumes_frozen_batch_without_retraining(self):
        import train_crawl_agent as trainer
        self.batch("cycle-0000")
        args = SimpleNamespace(forever=False, cycles=1)
        with (patch.object(trainer.storage,"configure"),
              patch.object(trainer.storage,"guard"),
              patch.object(trainer.storage,"maintain"),
              patch.object(trainer,"prepare",return_value=self.config),
              patch.object(trainer,"status") as status,
              patch.object(trainer,"audit_due"),
              patch.object(trainer,"run_batch",return_value={"state":"inconclusive"}) as batch,
              patch.object(trainer,"promote_confirmed",return_value=None),
              patch.object(trainer,"collect_parallel") as collect,
              patch.object(trainer,"train_behavioral_clone") as train):
            trainer.run_training(args,self.root)
        batch.assert_called_once()
        collect.assert_not_called()
        train.assert_not_called()
        self.assertEqual(status.call_args.kwargs["completed_cycles"],1)

    def test_confirmation_requires_whole_batch_and_handles_censoring(self):
        self.assertEqual(selection.confirmation_decision(games(5,10),games(5,20))["state"],"inconclusive")
        a,b=games(30,10),games(30,20)
        self.assertTrue(selection.confirmation_decision(a,b)["promote"])
        self.assertEqual(selection.confirmation_decision(b,a)["state"],"confirmed_worse")
        self.assertEqual(selection.confirmation_decision(a,a)["state"],"inconclusive")
        b[0]["terminal"]=False
        self.assertEqual(selection.confirmation_decision(a,b)["state"],"inconclusive")

    def test_pairing_by_seed_not_order_and_duplicates_rejected(self):
        a,b=games(30,10),games(30,20)
        self.assertTrue(selection.confirmation_decision(a,list(reversed(b)))["promote"])
        b[-1]=b[0]
        self.assertFalse(selection.confirmation_decision(a,b)["promote"])

    def test_one_sided_fifth_percentile(self):
        protocol={**selection.PROTOCOL,"confirmation_pairs":5,"bootstrap_resamples":2000}
        a=games(5,100)
        b=[{**r,"score":100+d} for r,d in zip(a,[-42,84,51,11,225])]
        result=selection.confirmation_decision(a,b,protocol)
        self.assertGreater(result["lower_one_sided_95"],0)

    def test_freeze_resume_seed_quarantine_and_no_lucky_retries(self):
        folder=self.batch()
        first=(folder/"manifest.json").read_bytes()
        self.assertEqual(self.batch(),folder)
        self.assertEqual(first,(folder/"manifest.json").read_bytes())
        seeds=json.loads(first)["seeds"]
        self.assertEqual(len(set(seeds)),30)
        self.assertTrue(all(held_out_seed(s) for s in seeds))
        self.assertEqual(self.batch("another-batch"),folder)
        audit=self.batch("audit-5","audit")
        self.assertFalse(set(seeds)&set(json.loads((audit/"manifest.json").read_text())["seeds"]))
        self.candidate.write_bytes(b"changed")
        with self.assertRaises(ValueError):self.batch()

    def test_no_interim_decision_resume_and_atomic_promotion(self):
        folder=self.batch()
        manifest=json.loads((folder/"manifest.json").read_text())
        seed=manifest["seeds"][0]
        selection.write(folder/"results"/f"champion-{seed}.json",{
            "seed":seed,"terminal":True,"score":10,"frozen_model_sha256":manifest["hashes"]["champion"]})
        calls=[]
        def runner(work,seed,steps,**kwargs):
            self.assertFalse((folder/"decision.json").exists())
            self.assertNotIn("replay_path",kwargs)
            self.assertEqual(kwargs["data_role"],"confirmation")
            calls.append(seed)
            return {"seed":seed,"terminal":True,"score":20 if kwargs["policy_version"]=="candidate" else 10}
        result=selection.run_batch(folder,runner)
        self.assertEqual(len(calls),59)
        self.assertTrue(result["promote"])
        self.assertEqual(selection.run_batch(folder,lambda *a,**k:self.fail("reran complete batch")),result)
        promoted=selection.promote_confirmed(self.root,folder)
        self.assertEqual(promoted.read_bytes(),b"candidate")
        self.assertEqual(selection.promote_confirmed(self.root,folder),promoted)

    def test_crash_does_not_abort_batch_or_allow_promotion(self):
        folder=self.batch()
        count=[]
        def runner(work,seed,steps,**kwargs):
            count.append(1)
            if kwargs["policy_version"]=="candidate":raise RuntimeError("test failure")
            return {"seed":seed,"terminal":True,"score":10}
        decision=selection.run_batch(folder,runner)
        self.assertEqual(len(count),60)
        self.assertEqual(decision["state"],"inconclusive")
        self.assertIsNone(selection.promote_confirmed(self.root,folder))

    def test_prohibit_held_out_collection_and_replay_ingestion(self):
        seed=str((0xD<<60)|123)
        with self.assertRaises(ValueError):assert_training_seed(seed)
        with self.assertRaises(ValueError):run_episode(self.root/"actor",seed,10)
        with self.assertRaises(ValueError):run_episode(self.root/"actor",seed,10,replay_path=self.root/"bad",data_role="confirmation")
        path=self.root/"replay.jsonl"
        path.write_text(json.dumps({"episode_seed":seed,"observation":{"schema":"crawl-general-v1"}})+"\n")
        path.with_suffix(".result.json").write_text('{"steps":1}')
        with self.assertRaises(ValueError):rows_from_replay(path)

    def test_audit_schedule_and_no_promotion(self):
        with patch.object(selection,"run_batch",return_value={"state":"audit_complete","promote":False}) as run:
            selection.audit_due(self.root,self.config,4)
            run.assert_not_called()
            selection.audit_due(self.root,self.config,5)
            run.assert_called_once()
        folder=self.root/"evaluations/audits/after-0005-cycles"
        def runner(work,seed,steps,**kwargs):
            return {"seed":seed,"terminal":True,"score":20 if kwargs["policy_version"]=="candidate" else 10}
        result=selection.run_batch(folder,runner)
        self.assertEqual(result["state"],"audit_complete")
        self.assertFalse(result["promote"])

    def test_run_lock_prevents_concurrent_mutation(self):
        with selection.run_lock(self.root):
            with self.assertRaises(RuntimeError):
                with selection.run_lock(self.root):pass


if __name__=="__main__":unittest.main()
