import tempfile
import unittest
from pathlib import Path
import torch
import critic_experiment as c
from bootstrap_repair import write


class CriticTests(unittest.TestCase):
    def setUp(self): torch.set_num_threads(1)

    def test_pool_order_and_memory(self):
        actions=torch.zeros(4,626)
        original=c.pool_actions(actions)
        actions[:,-3]=.7
        self.assertFalse(torch.equal(original,c.pool_actions(actions)))
        self.assertTrue(torch.equal(c.pool_actions(actions),c.pool_actions(actions.flip(0))))

    def test_real_features_expose_memory_only_to_rich_input(self):
        from model import tensor_for_actions
        import copy
        actions=[{'kind':'MOVE','dx':1,'dy':0}]
        state={'schema':'crawl-general-v1','actions':actions}
        before=tensor_for_actions(state,actions)
        changed=copy.deepcopy(state)
        changed['visit_memory']={'step':100,'since_discovery':80,'since_new_tile':70,
                                 'tiles':{'0:0':[40,100],'1:0':[20,90]}}
        after=tensor_for_actions(changed,actions)
        self.assertTrue(torch.equal(before[0],after[0]))
        self.assertFalse(torch.equal(c.pool_actions(before[1]),c.pool_actions(after[1])))

    def test_terminal_and_censoring(self):
        self.assertIsNone(c.remaining_targets([10,20],40,False))
        torch.testing.assert_close(c.remaining_targets([10,20],40,True),torch.tensor([.03,.02]))
        # Native terminal adjustments may make remaining return negative.
        self.assertLess(c.remaining_targets([50],40,True).item(),0)

    def test_split(self):
        groups=c.seed_plan(123,4,3,2)
        self.assertEqual(len(set(sum(groups.values(),[]))),9)
        with self.assertRaises(ValueError): c.seed_plan(0xC<<60,2,2,2)

    def test_seed_balanced_metrics(self):
        games=[{'context':torch.zeros(n,2),'targets':torch.full((n,),float(i))}
               for i,n in enumerate([1,99])]
        _,y,w=c.tensors(games,False)
        self.assertAlmostEqual(c.metrics(torch.zeros_like(y),y,w)['target_mean'],.5,places=6)

    def test_fit_and_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);groups=c.seed_plan(200,2,2,2)
            torch.manual_seed(11)
            for split,seeds in groups.items():
                for seed in seeds:
                    path=root/'games'/split/str(seed);path.mkdir(parents=True)
                    row={'seed':str(seed),'context':torch.randn(8,4),
                         'navigation':torch.randn(8,3),'targets':torch.randn(8)}
                    torch.save(row,path/'samples.pt')
                    write(path/'result.json',{'samples':8,'censored':False})
            result=c.fit(root,groups,2,lambda **_:None)
            self.assertTrue(result['valid'])
            saved=torch.load(root/'navigation.pt',weights_only=False)
            net=c.Critic(saved['size']);net.load_state_dict(saved['state_dict'])
            self.assertTrue(torch.isfinite(net(torch.zeros(1,saved['size']))).all())
            # Re-reading leaves test labels out of training and reproduces results.
            self.assertEqual(len(c.dataset(root,'train',groups['train'])),2)


if __name__=='__main__': unittest.main()
