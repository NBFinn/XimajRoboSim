"""RoboSim 2: echte Kernabläufe, Speicherfehler und konservative räumliche Suche."""
import copy
import json
import math
import os
from pathlib import Path
import random
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ximaj_robosim'))
from sim import Simulation, SceneObj
from spatial import SupportIndex
from diagnostics import inspect_cell
from project_store import write_project, read_project, validate_document
from opcua_client import _set_sim, _sim_value, _cast
from asyncua import ua


def cell(src):
    s = Simulation()
    s.scene = []
    s.stop_on_collision = False
    s.load_program(src)
    s.start()
    s.tick(.02)
    return s


class Flow(unittest.TestCase):
    def test_pause_freezes_world_and_preserves_wait_condition(self):
        s = cell('DEF main()\nWAIT FOR $IN[9]\n$OUT[8]=TRUE\nEND')
        b = SceneObj('Band', 'conveyor', size=[1000, 500, 100])
        p = SceneObj('Teil', 'workpiece', pos=[0, 0, 100], obstacle=False, graspable=True)
        s.scene = [b, p]
        s.tick(.02)
        s.pause_all()
        position, t = list(p.pos), s.t
        s.tick(1)
        self.assertEqual(p.pos, position)
        self.assertEqual(s.t, t)
        self.assertTrue(s.start_all())
        s.tick(.02)
        self.assertEqual(s.state, 'wait')
        self.assertFalse(s.io.get_out(8))
        s.io.set_in(9, True)
        s.tick(.02)
        self.assertTrue(s.io.get_out(8))

    def test_individual_pause_retains_delay_and_pulse(self):
        s = cell('DEF main()\nPULSE($OUT[8],TRUE,1)\nWAIT SEC 1\n$OUT[9]=TRUE\nEND')
        r = s.active
        self.assertEqual(r.state, 'wait')
        r.pause()
        for _ in range(110):
            s.tick(.01)
        self.assertTrue(s.io.get_out(8))
        r.resume()
        for _ in range(40):
            s.tick(.01)
        self.assertFalse(s.io.get_out(9))
        for _ in range(70):
            s.tick(.01)
        self.assertFalse(s.io.get_out(8))
        self.assertTrue(s.io.get_out(9))

    def test_duplicate_start_does_not_repeat_side_effects(self):
        s = cell('DEF main()\n$OUT[7]=TRUE\nWAIT FOR $IN[5]\nEND')
        generator = s.gen
        s.io.set_out(7, False)
        self.assertFalse(s.start())
        self.assertFalse(s.start_all())
        self.assertIs(s.gen, generator)
        s.tick(.04)
        self.assertFalse(s.io.get_out(7))

    def test_breakpoint_before_effect_and_local_variables(self):
        s = Simulation()
        s.scene = []
        s.load_program('DEF main()\nDECL INT count=3\n$OUT[6]=TRUE\nWAIT FOR $IN[3]\nEND')
        s.active.breakpoints = {3}
        s.start()
        s.tick(.02)
        self.assertEqual(s.state, 'paused')
        self.assertFalse(s.io.get_out(6))
        self.assertTrue(s.world_paused)
        self.assertIn(3, s.interp.debug_variables().values())
        self.assertTrue(s.interp.frames)
        s.resume()
        s.tick(.02)
        self.assertTrue(s.io.get_out(6))
        self.assertEqual(s.state, 'wait')
        other = Simulation()
        other.from_dict(s.to_dict())
        self.assertEqual(other.active.breakpoints, {3})

    def test_backlog_bounded_and_time_not_lost(self):
        s = Simulation()
        s.scene = []
        s.speed_factor = 100
        s.max_substeps = 10
        s.tick(.1)
        self.assertEqual(s.performance['substeps'], 10)
        self.assertAlmostEqual(s.t + s.pending_dt, 10.)
        self.assertGreater(s.pending_dt, 9)
        s.pause_all()
        self.assertEqual(s.pending_dt, 0)
        with self.assertRaises(ValueError):
            s.tick(float('nan'))


class Storage(unittest.TestCase):
    def test_atomic_write_and_previous_version_backup(self):
        s = Simulation()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'test.xrsim'
            original = s.to_dict()
            write_project(p, original)
            changed = copy.deepcopy(original)
            changed['robots'][0]['program'] = 'DEF next()\nEND'
            write_project(p, changed)
            self.assertEqual(read_project(p), changed)
            self.assertEqual(read_project(str(p) + '.bak'), original)
            with patch('project_store.os.replace', side_effect=OSError('Simulierter Schreibfehler')):
                with self.assertRaises(OSError):
                    write_project(p, original)
            self.assertEqual(read_project(p), changed)
            self.assertFalse(list(Path(d).glob('*.tmp*')))

    def test_invalid_data_does_not_replace_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'test.xrsim'
            data = Simulation().to_dict()
            write_project(p, data)
            previous = p.read_bytes()
            data['robots'][0]['q'][0] = float('nan')
            with self.assertRaises(ValueError):
                write_project(p, data)
            self.assertEqual(p.read_bytes(), previous)
        with self.assertRaises(ValueError):
            validate_document({'scene': [dict(name='a', kind='box', parent='b'), dict(name='b', kind='box', parent='a')]})

    def test_diagnostics_are_observations_without_program_execution(self):
        s = Simulation()
        s.src = 'DEF main()\n$OUT[7]=TRUE\nEND'
        s.scene = [SceneObj('Doppelt'), SceneObj('Doppelt')]
        s.links = [dict(src=('Fehlt', 'Outputs_Port_1'), dst=(s.active.name, 'Inputs_Port_2'))]
        issues = inspect_cell(s)
        self.assertGreaterEqual(sum(i.level == 'Fehler' for i in issues), 2)
        self.assertFalse(s.io.get_out(7))
        self.assertIsNone(s.gen)


class Spatial(unittest.TestCase):
    def test_released_part_cannot_remain_below_ground(self):
        s = Simulation()
        p = SceneObj('Teil', 'workpiece', pos=[100, 0, -54], obstacle=False, graspable=True)
        s.scene = [p]
        s._update_world(.01)
        self.assertEqual(p.pos[2], 0)

    def test_candidate_search_matches_full_exact_query(self):
        rng = random.Random(731)
        s = Simulation()
        s.scene = [SceneObj(str(n), pos=[rng.uniform(-2000, 2000), rng.uniform(-2000, 2000), rng.uniform(0, 100)],
                            rot=[rng.uniform(-180, 180), 5 if n % 13 == 0 else 0, 0],
                            size=[rng.uniform(50, 1500), rng.uniform(50, 1500), 100],
                            graspable=n % 17 == 0) for n in range(90)]
        s.scene += [SceneObj('Große Fläche', size=[50000, 50000, 10]), SceneObj('Kurve', 'conveyor_arc')]
        probes = [SceneObj('Probe', pos=[rng.uniform(-2500, 2500), rng.uniform(-2500, 2500), 300]) for _ in range(180)]
        expected = [s.support_z(p) for p in probes]
        s._support_index = SupportIndex(s.scene)
        self.assertEqual([s.support_z(p) for p in probes], expected)
        moving = s.scene[0]
        moving.pos[0] = 20000
        p = SceneObj('Probe', pos=[20000, moving.pos[1], 300])
        actual = s.support_z(p)
        s._support_index = None
        self.assertEqual(s.support_z(p), actual)

    def test_transform_cache_is_invalidated_on_direct_pose_change(self):
        o = SceneObj('Test')
        before = o.matrix()
        before[0, 3] = 999
        self.assertEqual(o.matrix()[0, 3], 0)
        o.pos[0] = 123
        o.rot[0] = 30
        m = o.matrix()
        self.assertEqual(m[0, 3], 123)
        import numpy as np
        self.assertTrue(np.allclose(o.inverse_matrix() @ m, np.eye(4)))


class Targets(unittest.TestCase):
    def test_types_and_missing_robot_do_not_silently_alias(self):
        s = Simulation()
        _set_sim(s, 'IN:1', 'false')
        self.assertFalse(s.io.get_in(1))
        for target, value in [('IN:0', True), ('SPEED', 0), ('OVERRIDE', float('inf')), ('OUT:1', 'invalid')]:
            with self.assertRaises(ValueError):
                _set_sim(s, target, value)
        with self.assertRaises(ValueError):
            _sim_value(s, 'AXIS:NichtVorhanden:1')
        with self.assertRaises(ValueError):
            _cast(256, ua.VariantType.Byte)
        self.assertEqual(len(_sim_value(s, 'JOINTS:' + s.active.name)), 6)
        self.assertEqual(len(_sim_value(s, 'POSE:' + s.active.name + ':WORLD')), 6)


if __name__ == '__main__':
    unittest.main(verbosity=2)
