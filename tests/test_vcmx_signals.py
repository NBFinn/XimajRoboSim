"""Signal graph, colour classification, edge creation and reset regressions."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ximaj_robosim'))
from sim import IO, SceneObj, Simulation
from rsc_parser import RNode
import vcmx_import

LOCAL = Path(r'C:\Users\FinnStetter\OneDrive - Ximaj IT-Solutions GmbH\Dokumente\KUKA\iiQWorks.Sim 1.3\My Models\Untitled.vcmx')


class Signals(unittest.TestCase):
    def test_color_lamp_trigger_edges_and_reset(self):
        s = Simulation()
        sensor = SceneObj('beam', 'sensor', size=(100, 100, 100), obstacle=False)
        color = SceneObj('colour', 'color_sensor', size=(100, 100, 100), obstacle=False)
        color.color_outs = {'ROT': 0, 'BLAU': 0}
        lamp = SceneObj('display', 'lamp', obstacle=False)
        creator = SceneObj('creator', 'spawner', (1000, 0, 0), obstacle=False)
        creator.colors = ['#ff0000', '#0000ff']
        part = SceneObj('part', 'workpiece', size=(20, 20, 20), color='#ff0000', graspable=True, obstacle=False)
        s.scene = [sensor, color, lamp, creator, part]
        s.links = [
            {'src': ('beam', 'SensorBooleanSignal'), 'dst': ('colour', 'ColorTrigger')},
            {'src': ('beam', 'SensorBooleanSignal'), 'dst': ('creator', 'CreationSignal')},
            {'src': ('colour', 'ROT'), 'dst': ('display', 'ROT')},
            {'src': ('colour', 'BLAU'), 'dst': ('display', 'BLAU')},
        ]
        s.wire_links()
        s.tick(.1)
        self.assertTrue(s.io.get_in(color.detected))
        self.assertTrue(s.io.get_in(color.color_outs['ROT']))
        self.assertFalse(s.io.get_in(color.color_outs['BLAU']))
        self.assertEqual(lamp.lit_color, (1., 0., 0.))
        self.assertEqual(creator.spawned, 1)
        first_color = next(o.color for o in s.scene if getattr(o, '_runtime_created', False))
        s.tick(5)
        self.assertEqual(creator.spawned, 1)
        part.pos[0] = 500
        s.tick(.1)
        self.assertIsNone(lamp.lit_color)
        self.assertFalse(s.io.get_in(color.detected))
        part.pos[0] = 0
        part.color = '#0000ff'
        s.tick(.1)
        self.assertEqual(creator.spawned, 2)
        self.assertEqual(lamp.lit_color, (0., 0., 1.))
        s.reset_world()
        self.assertEqual(creator.spawned, 0)
        self.assertIsNone(lamp.lit_color)
        self.assertFalse(any(s.io.inp) or any(s.io.out))
        s.world_paused = False
        s.tick(.1)
        self.assertEqual(creator.spawned, 1)
        self.assertEqual(next(o.color for o in s.scene if getattr(o, '_runtime_created', False)), first_color)

    def test_robot_scoping_fanout_and_serialization(self):
        s = Simulation()
        s.active.name = 'robot_A'
        r2 = s.add_robot(name='robot_B')
        belt = SceneObj('belt', 'conveyor', size=(2000, 400, 800), obstacle=False)
        creator = SceneObj('creator', 'spawner', (0, 0, 800), obstacle=False)
        s.scene = [belt, creator]
        s.links = [
            {'src': ('robot_B', 'Outputs_Port_1'), 'dst': ('belt', 'Engine')},
            {'src': ('robot_A', 'Outputs_Port_1'), 'dst': ('creator', 'CreationSignal')},
        ]
        s.wire_links()
        self.assertEqual(belt.io, 1)
        self.assertEqual(creator.trigger, 1)
        s.robots[0].io.set_out(1, True)
        s.tick(.1)
        self.assertEqual(creator.spawned, 1)
        part = next(o for o in s.scene if o.graspable)
        self.assertEqual(part.pos[0], 0)
        r2.io.set_out(1, True)
        s.tick(.1)
        self.assertGreater(part.pos[0], 0)
        self.assertTrue(s.robots[0].io.get_out(1))
        loaded = Simulation()
        loaded.from_dict(json.loads(json.dumps(s.to_dict())))
        self.assertEqual(loaded.links, s.links)
        self.assertEqual(loaded.scene[1].trigger, 1)
        old = SceneObj.from_dict({'name': 'old', 'kind': 'spawner'})
        self.assertEqual((old.trigger, old.colors, old.inputs, old.color_outs), (0, [], {}, {}))
        self.assertTrue(IO.is_virtual(2001))
        self.assertFalse(IO.is_virtual(1024))
        s.io.set_in(4096, True)
        self.assertTrue(s.io.get_in(4096))
        s.reset_world()
        self.assertFalse(r2.io.get_out(1))

    def test_connection_names_with_underscores_and_pointer(self):
        def var(name, value):
            return RNode('Variable', [], [RNode('Name', [f'"{name}"']), RNode('Value', [f'"{value}"'])])
        def functionality(kind, name, pointer=None):
            vs = [var('Name', name)]
            if pointer:
                vs.append(var('Signal', pointer))
            return RNode('Functionality', [kind], [RNode('VariableSpace', [], vs)])
        def comp(name, *fs):
            return RNode('Node', ['rSimResource'], [RNode('Name', [f'"{name}"']), *fs])
        source = comp('beam_with_under scores', functionality('rSimBoolSignal', 'SensorBooleanSignal'))
        target = comp('color_with_under scores', functionality('rSimBoolSignal', 'ColorTrigger'),
                      functionality('rSimInterface', 'Conn_OldName_beam_with_under scores_SensorBooleanSignal', 'ColorTrigger'))
        s = Simulation()
        s.scene = [SceneObj(source.name(), 'sensor'), SceneObj(target.name(), 'color_sensor')]
        log = []
        vcmx_import._read_links([source, target], s, log)
        self.assertEqual(s.links, [{'src': (source.name(), 'SensorBooleanSignal'), 'dst': (target.name(), 'ColorTrigger')}])
        self.assertTrue(any('Verbindung:' in line for line in log))

    def test_interval_mode_and_own_beam(self):
        s = Simulation()
        c = SceneObj('creator', 'spawner', (1000, 0, 0), obstacle=False)
        c.interval = .2
        sensor = SceneObj('color', 'color_sensor', obstacle=False)
        sensor.color_outs = {'ROT': 2001}
        sensor.detected = 2002
        part = SceneObj('part', 'workpiece', color='#ff0000', graspable=True, obstacle=False)
        s.scene = [c, sensor, part]
        s.tick(.3)
        self.assertEqual(c.spawned, 1)
        self.assertEqual(next(o.color for o in s.scene if getattr(o, '_runtime_created', False)), c.part_color)
        self.assertTrue(s.io.get_in(2001))
        self.assertTrue(s.io.get_in(2002))

    @unittest.skipUnless(LOCAL.exists(), 'Lokale Testdatei fehlt')
    def test_untitled_program_connections_and_color(self):
        s = Simulation()
        report = vcmx_import.import_file(s, str(LOCAL))
        self.assertTrue(s.links)
        self.assertTrue(report['main_program'])
        creator = next(o for o in s.scene if o.kind == 'spawner')
        self.assertGreater(creator.trigger, 0)
        self.assertGreater(len(creator.colors), 1)
        s.stop_on_collision = False
        s.start()
        for _ in range(300):
            s.tick(.1)
        self.assertGreater(creator.spawned, 0, s.message)
        engines = [x for x in s.links if x['dst'][1] == 'Engine']
        self.assertTrue(engines)
        link = engines[0]
        robot = next(r for r in s.robots if r.name == link['src'][0])
        belt = next(o for o in s.scene if o.name == link['dst'][0])
        port = int(link['src'][1].rsplit('_', 1)[1])
        robot.io.set_out(port, False)
        self.assertFalse(s._driven(belt, belt.io))
        robot.io.set_out(port, True)
        self.assertTrue(s._driven(belt, belt.io))
        sensor = next(o for o in s.scene if o.kind == 'color_sensor')
        s.stop_all()
        # Isolate the imported beam from transported parts and the trigger source.
        s.scene = [o for o in s.scene if not o.graspable]
        trigger_link = next(x for x in s.links if x['dst'] == (sensor.name, 'ColorTrigger'))
        trigger_sensor = next(o for o in s.scene if o.name == trigger_link['src'][0])
        for beam in (sensor, trigger_sensor):
            s.scene.append(SceneObj('red_' + beam.name, 'workpiece',
                                    [beam.pos[0], beam.pos[1], beam.pos[2] - 10], size=(20, 20, 20),
                                    color='#ff0000', obstacle=False, graspable=True))
        s.tick(.01)
        self.assertTrue(s.io.get_in(sensor.color_outs['ROT']))
        self.assertFalse(s.io.get_in(sensor.color_outs['BLAU']))


if __name__ == '__main__':
    unittest.main()
