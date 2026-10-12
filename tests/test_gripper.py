import sys
from pathlib import Path
import unittest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ximaj_robosim'))
from sim import Simulation, SceneObj


class GripperTests(unittest.TestCase):
    def setUp(self):
        self.sim = Simulation()
        self.robot = self.sim.active
        self.tcp = self.robot.tcp_world()[:3, 3].copy()
        self.robot.tool.grip_out = 4
        self.robot.tool.grip_range = 20

    def part(self, delta=(0, 0, 0), size=(20, 20, 20), name='Teil'):
        p = self.tcp + np.asarray(delta) - [0, 0, size[2] / 2]
        o = SceneObj(name, 'workpiece', pos=list(p), size=list(size), graspable=True, obstacle=False)
        self.sim.scene.append(o)
        return o

    def test_output_four_closes_and_opens(self):
        p = self.part()
        self.sim.io.set_out(1, True)  # Teile-Erzeuger soll den Greifer nicht schließen.
        self.robot.update_gripper()
        self.assertFalse(p.attached)
        self.sim.io.set_out(4, True)
        self.robot.update_gripper()
        self.assertEqual(p.attached_to, self.robot.name)
        self.sim.io.set_out(4, False)
        self.robot.update_gripper()
        self.assertFalse(p.attached)

    def test_part_arrives_after_close(self):
        p = self.part((200, 0, 0))
        self.sim.io.set_out(4, True)
        self.robot.update_gripper()
        self.assertFalse(p.attached)
        p.pos[0] -= 200
        self.robot.update_gripper()
        self.assertTrue(p.attached)

    def test_at_most_one_part_per_robot(self):
        a, b = self.part(name='A'), self.part(name='B')
        self.sim.io.set_out(4, True)
        for _ in range(3):
            self.robot.update_gripper()
        self.assertEqual(sum(p.attached for p in (a, b)), 1)

    def test_large_part_is_not_picked_from_far_side(self):
        p = self.part((0, 150, 0), (1000, 20, 20))
        self.sim.io.set_out(4, True)
        self.robot.update_gripper()
        self.assertFalse(p.attached)  # Die alte Kugelprüfung würde dieses Teil aus 150 mm greifen.

    def test_rotated_part_surface(self):
        p = self.part((0, 80, 0), (200, 20, 20))
        p.rot = [90, 0, 0]
        self.sim.io.set_out(4, True)
        self.robot.update_gripper()
        self.assertTrue(p.attached)

    def test_signal_conflict_is_visible(self):
        self.sim.links = [{'src': (self.robot.name, 'Outputs_Port_4'), 'dst': ('Creator', 'CreationSignal')}]
        self.assertEqual(self.robot.gripper_info()['conflicts'], ['Creator'])

    def test_part_follows_tool_and_keeps_release_pose(self):
        p = self.part()
        self.sim.io.set_out(4, True)
        self.robot.update_gripper()
        before = list(p.pos)
        self.robot.q[0] += 15
        self.robot.update_gripper()
        self.assertNotEqual(p.pos, before)
        release = list(p.pos)
        self.sim.io.set_out(4, False)
        self.robot.update_gripper()
        self.robot.q[0] += 15
        self.robot.update_gripper()
        self.assertEqual(p.pos, release)


if __name__ == '__main__':
    unittest.main(verbosity=2)
