"""Headless regression tests for model editing, diagnostics and traces."""
import csv
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ximaj_robosim'))
from sim import Simulation, SceneObj
from kinematics import MODELS, inv
import editing as ed
from analysis import analyze
from sim_trace import Recorder


class EditingTests(unittest.TestCase):
    def setUp(self):
        self.s = Simulation()

    def obj(self, name='part', **kwargs):
        o = SceneObj(name, **kwargs)
        self.s.scene.append(o)
        return o

    def test_copy_paste_deep_names_and_group_children(self):
        a = self.obj()
        b = self.obj('other', pos=(300, 0, 0))
        g = ed.group(self.s, [a, b])
        clip = ed.copy(self.s, [g])
        a.size[0] = 321
        pasted = ed.paste(self.s, clip)
        by_name = {o.name: o for o in pasted}
        self.assertEqual(by_name['part (2)'].size[0], 200)
        self.assertEqual(by_name['part (2)'].parent, 'Gruppe (2)')
        np.testing.assert_allclose(by_name['part (2)'].pos, [200, 200, 0])
        self.assertIn('part (3)', [o.name for o in ed.paste(self.s, clip)])
        self.assertEqual(clip[0]['name'], 'part')

    def test_group_ungroup_move_and_delete_references(self):
        a, b = self.obj(), self.obj('b', pos=(200, 0, 0))
        g = ed.group(self.s, [a, b], 'assembly')
        self.assertFalse(g.obstacle or g.visible)
        ed.move(self.s, g, 50, 0, 0)
        np.testing.assert_allclose(a.pos, [50, 0, 0])
        children = ed.ungroup(self.s, g)
        self.assertEqual(children, [a, b])
        self.assertIsNone(a.parent)
        g = ed.group(self.s, children)
        self.s.links = [{'src': (a.name, 'signal'), 'dst': ('missing', 'signal')}]
        self.s.dimensions = [{'objects': [a.name]}, {'type': 'linear', 'pts': [[0,0,0], [1,0,0]], 'label': '1'}]
        ed.delete(self.s, [g])
        self.assertFalse(self.s.scene or self.s.links)
        self.assertEqual(len(self.s.dimensions), 1)

    def test_flange_attach_detach_and_cycle_rejection(self):
        o = self.obj(pos=(500, 200, 600), graspable=True)
        robot = self.s.active
        before = o.matrix().copy()
        ed.attach(self.s, o, robot.name+'@flange')
        np.testing.assert_allclose(o.matrix(), before, atol=1e-9)
        local = np.array(o.local)
        robot.q[0] += 30
        self.s.tick(.01)
        np.testing.assert_allclose(o.matrix(), robot.flange_world() @ local, atol=1e-8)
        ed.detach(self.s, o)
        before = o.matrix().copy()
        robot.q[0] += 30
        ed.update_hierarchy(self.s)
        np.testing.assert_allclose(o.matrix(), before, atol=1e-8)
        child = self.obj('child')
        ed.attach(self.s, child, o.name)
        with self.assertRaises(ValueError):
            ed.attach(self.s, o, child.name)

    def test_gripper_has_priority(self):
        o = self.obj()
        parent = self.obj('parent')
        ed.attach(self.s, o, parent.name)
        o.attached = True
        o.pos = [10, 20, 30]
        ed.move(self.s, parent, 100, 0, 0)
        np.testing.assert_allclose(o.pos, [10, 20, 30])

    def test_gripping_releases_old_fixture_parent(self):
        r = self.s.active
        tcp = r.tcp_world()[:3, 3]
        o = self.obj(pos=tcp-[0,0,100], graspable=True)
        fixture = self.obj('fixture', obstacle=False)
        ed.attach(self.s, o, fixture.name)
        r.io.set_out(r.tool.grip_out, True)
        r.update_gripper()
        self.assertTrue(o.attached)
        self.assertIsNone(o.parent)
        r.q[0] += 20
        r.update_gripper()
        dropped = o.matrix().copy()
        r.io.set_out(r.tool.grip_out, False)
        r.update_gripper()
        ed.move(self.s, fixture, 1000, 0, 0)
        np.testing.assert_allclose(o.matrix(), dropped, atol=1e-8)
        self.assertFalse(o.attached)

    def test_snap_align_local_move(self):
        target = self.obj('target', pos=(100, 200, 50), rot=(90, 0, 0), size=(300, 400, 100))
        o = self.obj(size=(20, 20, 20))
        ed.snap(self.s, o, target)
        np.testing.assert_allclose(o.pos, [100, 200, 150], atol=1e-8)
        ed.align(self.s, o, target)
        ed.move(self.s, o, 10, 0, 0, frame='local')
        np.testing.assert_allclose(o.pos, [100, 210, 150], atol=1e-8)
        ed.align(self.s, o, target, 'z')
        self.assertEqual(o.pos[2], 50)

    def test_pnp_straight_arc_and_occupied(self):
        first = self.obj('belt1', kind='conveyor', size=(1000, 300, 800))
        second = self.obj('belt2', kind='conveyor', pos=(1100, 0, 0), size=(1000, 300, 800))
        self.assertIsNone(ed.pnp(self.s, second))
        np.testing.assert_allclose(ed.conveyor_ends(first)[1], ed.conveyor_ends(second)[0])
        arc = self.obj('arc', kind='conveyor_arc', pos=(1600, 0, 0), size=(500, 300, 800))
        arc.radius = 500
        self.assertIsNone(ed.pnp(self.s, arc))
        np.testing.assert_allclose(ed.conveyor_ends(arc)[1], [2000, -500, 800], atol=1e-8)
        self.assertEqual(ed.conveyor_ends(arc)[2], -90)
        blocked = self.obj('blocked', kind='conveyor', pos=(1100, 0, 0), size=(1000, 300, 800))
        self.assertIsInstance(ed.pnp(self.s, blocked, radius=150), str)
        sensor = self.obj('sensor', kind='sensor', pos=(2050, -500, 800))
        self.assertIsNone(ed.pnp(self.s, sensor))
        np.testing.assert_allclose(sensor.pos, [2000, -500, 800], atol=1e-8)

    def test_measure_angle_dimensions_settings_persist(self):
        self.assertEqual(ed.measure([0,0,0], [3,4,0]), dict(dist=5., dx=3., dy=4., dz=0.))
        self.assertEqual(ed.angle([1,0,0], [0,0,0], [0,1,0]), 90)
        with self.assertRaises(ValueError):
            ed.angle([0,0,0], [0,0,0], [1,0,0])
        ed.add_dimension(self.s, 'linear', [[0,0,0], [3,4,0]])
        ed.add_dimension(self.s, 'angle', [[1,0,0], [0,0,0], [0,1,0]])
        parent = self.obj('parent')
        child = self.obj('child', pos=(300,0,0))
        ed.attach(self.s, child, parent.name)
        self.s.collision_ignore = {('Roboter 1', 'parent')}
        self.s.collision_enabled = False
        self.s.limit_warn_pct = 5
        self.s.show_limit_colors = True
        restored = Simulation()
        restored.from_dict(json.loads(json.dumps(self.s.to_dict())))
        self.assertEqual(restored.dimensions, self.s.dimensions)
        self.assertEqual(restored.collision_ignore, self.s.collision_ignore)
        self.assertFalse(restored.collision_enabled)
        self.assertTrue(restored.show_limit_colors)
        self.assertEqual(restored.limit_warn_pct, 5)
        self.assertEqual(restored.scene[1].parent, 'parent')
        restored.reset_world()
        self.assertEqual(restored.dimensions, self.s.dimensions)

    def test_mesh_origin_and_robot_frame_swap(self):
        o = self.obj(kind='mesh', rot=(90,0,0))
        o.mesh = (np.array([[-10.,-20.,0.], [10.,20.,40.], [10.,-20.,0.]]), np.array([[0,1,2]]))
        verts = o.mesh[0] @ o.matrix()[:3,:3].T + o.pos
        ed.set_origin(self.s, o, 'center')
        np.testing.assert_allclose(o.mesh[0] @ o.matrix()[:3,:3].T+o.pos, verts)
        self.assertIsInstance(ed.set_origin(self.s, self.obj('primitive'), 'center'), str)
        robot = self.s.active
        ed.attach(self.s, o, robot.name+'@base')
        before = o.matrix().copy()
        ed.move_robot_frame(self.s, robot, [100,0,0,0,0,0], 'world')
        np.testing.assert_allclose(o.matrix(), before, atol=1e-8)
        ed.move_robot_frame(self.s, robot, [200,0,0,0,0,0])
        np.testing.assert_allclose(o.pos, before[:3,3]+[100,0,0])
        root, tool, src, points = robot.root.copy(), robot.tool, robot.src, robot.waypoints
        robot.q[:] = 10000
        ed.swap_robot(self.s, robot, list(MODELS)[-1])
        np.testing.assert_allclose(robot.root, root)
        self.assertIs(robot.tool, tool)
        self.assertEqual(robot.src, src)
        self.assertIs(robot.waypoints, points)
        self.assertTrue(np.all(robot.q <= robot.model.limits[:,1]))

    def test_analysis_unreachable_gap_and_read_only(self):
        self.s.active.waypoints = [{'name': 'Impossible', 'pos': [1e6,0,0,0,0,0]}]
        self.obj('belt1', kind='conveyor', size=(1000,300,800))
        self.obj('belt2', kind='conveyor', pos=(1100,0,0), size=(1000,300,800))
        self.obj('sensor', kind='sensor', pos=(0,500,0), obstacle=False)
        self.s.links = [{'src': ('missing','signal'), 'dst': ('sensor','signal')}]
        before = self.s.to_dict()
        messages = analyze(self.s)
        self.assertTrue(any('Impossible' in m['text'] and 'nicht erreichbar' in m['text'] for m in messages))
        self.assertTrue(any('Förderbandlücke' in m['text'] for m in messages))
        self.assertTrue(any('fehlendes Objekt' in m['text'] for m in messages))
        self.assertEqual(self.s.to_dict(), before)

    def test_analysis_200_objects_performance(self):
        self.s.collision_enabled = False
        for i in range(200):
            self.obj(f'box{i}', pos=(i*300,0,0))
        start = time.perf_counter()
        analyze(self.s)
        self.assertLess(time.perf_counter()-start, 1.)

    def test_recorder_series_changes_window_csv(self):
        recorder = Recorder(self.s, max_seconds=.05)
        recorder.start()
        self.s.tick(.03)
        self.s.active.q[0] += 5
        self.s.io.set_out(4, True)
        self.s.tick(.03)
        t, q = recorder.series(self.s.active.name, 'q')
        self.assertEqual(q.shape, (len(t),6))
        self.assertEqual(len(t), len(recorder.series(self.s.active.name, 'tcp')[0]))
        self.assertTrue(any(4 in d for d in recorder.series(self.s.active.name, 'outputs')[1]))
        self.assertGreater(recorder.stats()['max_speeds'][self.s.active.name], 0)
        self.s.tick(.1)
        self.assertLessEqual(recorder.samples[-1]['t']-recorder.samples[0]['t'], .05+1e-9)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'trace.csv'
            recorder.to_csv(path)
            with path.open(encoding='utf-8', newline='') as f:
                rows = list(csv.reader(f))
            self.assertEqual(len(rows), len(recorder.samples)+1)
            self.assertEqual(rows[0][0], 't')
        recorder.stop()
        n = len(recorder.samples)
        self.s.tick(.02)
        self.assertEqual(len(recorder.samples), n)
        recorder.clear()
        self.assertEqual(recorder.series(self.s.active.name, 'q')[1].shape, (0,6))

    def test_limit_flags_entry_messages_and_stop(self):
        r = self.s.active
        self.s.limit_messages = True
        r.q[0] = r.model.limits[0,1]
        self.s.tick(.01)
        self.assertIn(0, r.near_limits)
        n = sum('Achsgrenze nahe:' in m for m in self.s.log)
        self.s.tick(.02)
        self.assertEqual(sum('Achsgrenze nahe:' in m for m in self.s.log), n)
        self.s.stop_at_limits = True
        self.s.collision_enabled = False
        r.load_program('DEF a()\nWAIT SEC 1\nEND')
        r.start()
        q = r.q.copy()
        self.s.tick(.01)
        self.assertEqual(r.state, 'stopped')
        np.testing.assert_allclose(r.q, q)
        self.assertIsNone(r.check_collision())


if __name__ == '__main__':
    unittest.main()
