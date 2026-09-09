import unittest
from pathlib import Path
from lupa import LuaRuntime

class GoalBridgeTest(unittest.TestCase):
    def runtime(self):
        lua=LuaRuntime()
        lua.execute('''
        tb_direct_actions={}; BOT={}; commands={}
        scan={cells={},reachable_adjacent=false}
        scan_hostiles=function() return scan end
        observe_encounter=function() end
        observe_wand_encounter=function() end
        liquid_fire_action=function() return false end
        survival_action=function() return false end
        movement_locked=function() return false end
        unsafe_square_action=function() return false end
        combat_wand_action=function() return false end
        you={confused=function() return false end}
        CONFUSED_MOVE_COMMANDS={['1:0']='CMD_MOVE_RIGHT'}
        map_key=function(x,y) return x..':'..y end
        crawl={do_commands=function(cmds)
          assert(#cmds==1,'exactly one command, not gsub return count')
          assert(type(cmds[1])=='string'); commands[#commands+1]=cmds[1]
        end}
        ''')
        lua.execute((Path(__file__).parent/'goal_bridge.lua').read_text())
        return lua
    def test_invisible_probe_single_string(self):
        lua=self.runtime()
        lua.execute("scan.cells={{x=1,y=0,invisible_monster=true}};goal_safety()")
        self.assertEqual(lua.globals().commands[1],'CMD_ATTACK_RIGHT')
    def test_never_probe_ally(self):
        lua=self.runtime()
        lua.execute("scan.cells={{x=1,y=0,invisible_monster=true,monster={}}};goal_safety()")
        self.assertEqual(lua.globals().commands[1],'CMD_WAIT')
    def test_melee_no_pursuit(self):
        lua=self.runtime();lua.execute('scan.reachable_adjacent=true;goal_safety()')
        self.assertEqual(lua.globals().commands[1],'CMD_AUTOFIGHT_NOMOVE')
    def test_resource_action_preempts_fallback(self):
        lua=self.runtime()
        lua.execute('survival_action=function() return true end;goal_safety()')
        self.assertIsNone(lua.globals().commands[1])
    def test_ally_rejection_consumes_turn(self):
        lua=self.runtime();lua.execute('BOT.ally_attack_rejected=true;goal_safety()')
        self.assertEqual(lua.globals().commands[1],'CMD_WAIT')
        self.assertFalse(lua.globals().BOT.ally_attack_rejected)
    def test_observation_exports_withheld_and_known_attack_ranges(self):
        lua=self.runtime()
        lua.execute('''
        level_key=function() return 'D:6' end
        travel={set_waypoint=function() end,waypoint_delta=function() return 0,0 end}
        view={get_map=function() return {{x=1,y=0,feature='floor',traversable=true}} end,
              withheld=function(x,y) return x==1 and y==0 end}
        you.ability_info=function() return {} end
        scan.monsters={{x=2,y=0,monster={range=function() return 7 end,
                                      reach_range=function() return 2 end}}}
        state={}; goal_observation(state)
        ''')
        s=lua.globals().state
        self.assertTrue(s.known['1:0'].withheld)
        self.assertEqual(s.attack_ranges['2:0'].reach,2)
        self.assertEqual(s.attack_ranges['2:0'].range,7)

if __name__=='__main__': unittest.main()
