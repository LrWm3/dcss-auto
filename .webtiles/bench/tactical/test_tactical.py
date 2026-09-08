import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from bench import Environment, make_rc
from experiment import recovered, retreat, options, key
from verify_resume import normalized
from export_model import lua_key


class TacticalTests(unittest.TestCase):
    def state(self, **changes):
        state=dict(hp=56,max_hp=56,monsters={},cells={},safe=True,status='',
                   poisoned=False,on_fire=False,berserk=False,cooldown=False,
                   confused=False,turn=100,seq=2)
        state.update(changes)
        return state

    def test_recovery_requires_hazards_cleared(self):
        self.assertTrue(recovered(self.state()))
        for change in ({'poisoned':True},{'on_fire':True},{'hp':55},
                       {'status':'on berserk cooldown'},{'safe':False},
                       {'monsters':{'1':{'name':'Eustachio'}}}):
            self.assertFalse(recovered(self.state(**change)))
        self.assertFalse(recovered({'terminal':'death'}))

    def test_retreat_avoids_enemy_and_unknown_terrain(self):
        state=self.state(monsters={'1':{'x':1,'y':0}},cells={
            '1:0':{'traversable':True,'feature':'floor'},
            '-1:0':{'traversable':True,'feature':'floor'},
            '-1:1':{'traversable':True,'feature':'floor','cloud':'steam'}})
        self.assertEqual(retreat(state),'w')
        self.assertEqual(retreat(self.state()),'wait')

    def test_rage_mask(self):
        s=self.state(monsters={'1':{'x':2,'y':0}})
        self.assertIn('berserk',options(s))
        self.assertNotIn('berserk',options({**s,'cooldown':True}))
        self.assertIsInstance(key(s),str)

    def test_export_key_matches_lua_features(self):
        self.assertEqual(lua_key(key(self.state())), '4|0|3|false|false|false')
        with self.assertRaises(ValueError):lua_key('(1, 2)')

    def test_no_action_sent_before_interpreter_confirmation(self):
        with tempfile.TemporaryDirectory() as temp:
            env=Environment(temp);env.state=self.state();env.child=Mock()
            env.child.expect_exact.side_effect=TimeoutError('menu')
            with self.assertRaises(TimeoutError):env.console('tb_request("wait")')
            env.child.send.assert_called_once_with('\x04')

    def test_unknown_action_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            env=Environment(temp)
            with self.assertRaises(ValueError):env.step('quit')

    def test_terminal_requires_reset(self):
        with tempfile.TemporaryDirectory() as temp:
            env=Environment(temp);env.state={'terminal':'death'}
            with self.assertRaisesRegex(RuntimeError,'reset'):env.step('tab')

    def test_replay_comparison_ignores_transport_not_gameplay(self):
        s=self.state()
        self.assertEqual(normalized(s),normalized({**s,'seq':99,'messages':{'1':'Welcome back'}}))
        self.assertNotEqual(normalized(s),normalized({**s,'hp':55}))
        self.assertNotEqual(normalized(s),normalized({**s,'turn':101}))

    def test_rc_keeps_source_and_adds_bridge_inside_lua(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'test.rc';make_rc(p);text=p.read_text()
            self.assertIn('local tb_original_ready = ready',text)
            self.assertTrue(text.endswith('>\ndump_order += tactical_dump\n'))

    def test_checkpoint_integrity_before_engine_launch(self):
        with tempfile.TemporaryDirectory() as temp:
            case=Path(temp)/'case';case.mkdir()
            (case/'case.json').write_text(json.dumps({'engine_sha256':'wrong'}))
            env=Environment(Path(temp)/'workers')
            with self.assertRaisesRegex(ValueError,'engine mismatch'):env.reset(case)
            self.assertIsNone(env.child)


if __name__=='__main__':unittest.main()
