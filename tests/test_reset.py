import sys,unittest
import numpy as np
sys.path.insert(0,r'C:\Users\FinnStetter\Documents\XimajRoboSim\ximaj_robosim')
from sim import Simulation,SceneObj
class ResetTests(unittest.TestCase):
    def test_rewind_parts_robot_signals_and_restart(self):
        s=Simulation(); b=SceneObj('belt','conveyor',[0,0,0],size=[2000,400,800]); p=SceneObj('original','workpiece',[0,0,800],graspable=True,obstacle=False); c=SceneObj('creator','spawner',[-500,0,800],obstacle=False); c.interval=.2
        s.scene=[b,p,c]; q=s.q.copy(); s.tick(.01)
        s.q=s.q+1; s.io.set_out(4,True)
        for _ in range(20):s.tick(.1)
        self.assertGreater(c.spawned,0); self.assertGreater(p.pos[0],0)
        s.reset_world()
        self.assertEqual(s.scene,[b,p,c]);self.assertEqual(p.pos,[0.,0.,800.]);self.assertEqual(c.spawned,0);self.assertEqual(s.t,0);self.assertFalse(s.io.get_out(4));np.testing.assert_allclose(s.q,q)
        s.tick(1);self.assertEqual(c.spawned,0)
        s.load_program('DEF a()\nWAIT SEC 1\nEND');s.start();s.tick(.5);self.assertGreater(c.spawned,0)
    def test_consumed_restored_deleted_not_restored_and_scene_replaced(self):
        s=Simulation();p=SceneObj('part','workpiece',[0,0,50],graspable=True,obstacle=False);sink=SceneObj('sink','sink',[0,0,0],size=[1000,1000,1000]);deleted=SceneObj('deleted')
        s.scene=[p,sink,deleted];s.tick(.01);self.assertNotIn(p,s.scene);s.scene.remove(deleted);s.reset_world();self.assertIn(p,s.scene);self.assertNotIn(deleted,s.scene)
        fresh=SceneObj('fresh');s.scene=[fresh];s.reset_world();self.assertEqual(s.scene,[fresh])
if __name__=='__main__':unittest.main()
