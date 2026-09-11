import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parent))
from evaluate import evaluate_model
from general_env import sha
from collect import run_episode
from train_model import FeatureCache


class PythonPerfTests(unittest.TestCase):
    def test_screen_cache_reuses_only_matching_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            model=root/'model.pt'; model.write_text('weights')
            def game(*args,**kwargs):
                return {'seed':args[1],'score':12,'terminal':True,
                        'data_role':'screen','model_sha256':sha(model)}
            with patch('evaluate.run_episode',side_effect=game) as actor, patch('selection.environment_identity',return_value={'version':1}):
                def run(seed='910000000000',steps=20):
                    return evaluate_model(model,root/'games',[seed],steps=steps,cache_dir=root/'cache')
                self.assertFalse(run()[0].get('cache_hit',False))
                self.assertTrue(run()[0]['cache_hit'])
                self.assertEqual(actor.call_count,1)
                run(steps=21); run(seed='910000000001')
                self.assertEqual(actor.call_count,3)
                model.write_text('different weights'); run()
                self.assertEqual(actor.call_count,4)
            with patch('evaluate.run_episode',side_effect=game) as actor, patch('selection.environment_identity',return_value={'version':2}):
                run(); self.assertEqual(actor.call_count,1)

    def test_evaluation_does_not_call_teacher(self):
        state={'schema':'crawl-general-v1','level':'D:1','turn':0,
               'actions':[{'kind':'WAIT'}], 'terminal':False}
        env=MagicMock()
        env.launch.return_value=state
        env.step.return_value={**state,'terminal':'death','score':1,'turn':1}
        env.works=[]
        policy=MagicMock(); policy.choose.return_value=(0,{'kind':'WAIT'})
        with tempfile.TemporaryDirectory() as tmp:
            model=Path(tmp)/'model'; model.write_text('weights')
            env.work_path=Path(tmp)
            with patch('collect.GeneralEnvironment',return_value=env), patch('collect.Policy.from_checkpoint',return_value=(policy,{})), patch('collect.choose_action',side_effect=AssertionError('unused teacher')):
                result=run_episode(tmp,'910000000000',20,model_path=model,snapshot=False,data_role='screen')
            self.assertEqual(result['score'],1)

    def test_feature_cache_is_bounded(self):
        cache=FeatureCache(limit=1)
        a={'actions':[{'kind':'WAIT'}]}; b={'actions':[{'kind':'WAIT'}]}
        with patch('train_model.tensor_for_actions',return_value='encoded') as encode:
            self.assertEqual(cache.get(a),cache.get(a))
            self.assertEqual(encode.call_count,1)
            cache.get(b); cache.get(a)
            self.assertEqual(encode.call_count,3)


if __name__=='__main__':
    unittest.main()
