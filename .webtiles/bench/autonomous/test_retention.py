import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from retention import prune


class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def file(self,name,data='heavy'):
        p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(json.dumps(data) if isinstance(data,dict) else data)
        return p

    def test_eight_cycle_boundary_and_permanent_evidence(self):
        self.file('latest_status.json',{'completed_cycles':9})
        files=[]
        for i in range(10):
            name=f'cycle-{i:04d}-0'
            self.file(f'replay/{name}.result.json',{'steps':1})
            files.append(self.file(f'actors/{name}/general-a/events.jsonl.gz'))
        save=self.file('actors/cycle-0000-0/truncations/case/checkpoint.cs')
        metadata=self.file('actors/cycle-0000-0/general-a/run.json',{})
        morgue=self.file('actors/cycle-0000-0/general-a/morgue/morgue-test.txt')
        cache=self.file('actors/cycle-0000-0/general-a/saves/test.db')
        replay=self.file('replay/cycle-0000-0.jsonl.gz')
        failed=self.file('failures/cycle-0000/events.jsonl')
        unknown=self.file('counterfactual/branch-0/general-a/events.jsonl')
        model=self.file('candidates/cycle-0000.pt')
        preview=prune(self.root,True)
        self.assertEqual(preview['files'],3)
        self.assertTrue(files[0].exists())
        result=prune(self.root)
        self.assertEqual(result['prune_cycles_before'],1)
        self.assertFalse(files[0].exists())
        self.assertFalse(cache.exists());self.assertFalse(replay.exists())
        self.assertTrue(all(p.exists() for p in files[1:]+[save,metadata,morgue,failed,unknown,model]))
        self.assertEqual(prune(self.root)['files'],0)

    def test_protect_incomplete_work_and_symlink_targets(self):
        self.file('latest_status.json',{'completed_cycles':10})
        incomplete=self.file('actors/cycle-0000-0/general-a/events.jsonl')
        target=self.file('protected/events.jsonl')
        self.file('replay/cycle-0000-1.result.json',{'steps':1})
        folder=self.root/'actors/cycle-0000-1';folder.mkdir(parents=True)
        (folder/'general-link').symlink_to(target.parent,target_is_directory=True)
        self.assertEqual(prune(self.root)['files'],0)
        self.assertTrue(incomplete.exists());self.assertTrue(target.exists())

    def test_confirmation_audit_and_counterfactual_completion(self):
        self.file('latest_status.json',{'completed_cycles':14})
        deleted=[];preserved=[]
        for kind,label in [('confirmations','cycle-0000-confirmation-v1'),('audits','after-0005-cycles')]:
            base=f'evaluations/{kind}/{label}'
            self.file(base+'/decision.json',{'state':'inconclusive'})
            self.file(base+'/manifest.json',{'seeds':['1','2']})
            self.file(base+'/results/champion-1.json',{'policy_version':'champion','seed':'1'})
            self.file(base+'/results/candidate-2.json',{'error':'crash'})
            deleted.append(self.file(base+'/games/champion/1/general-a/events.jsonl.gz'))
            preserved.append(self.file(base+'/games/candidate/2/general-a/events.jsonl.gz'))
        cf='counterfactual/cycle-0000'
        self.file(cf+'/completed.json',{'complete':True})
        deleted.append(self.file(cf+'/branch-0/general-a/terminal.txt'))
        preserved.append(self.file('counterfactual/cycle-0001/branch-0/general-a/terminal.txt'))
        prune(self.root)
        self.assertTrue(all(not p.exists() for p in deleted))
        self.assertTrue(all(p.exists() for p in preserved))


if __name__ == '__main__':
    unittest.main()
