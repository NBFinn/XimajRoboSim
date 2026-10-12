"""VC runtime regression tests, including original local component scripts."""
import copy
import json
from pathlib import Path
import sys
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ximaj_robosim'))
from sim import SceneObj, Simulation
from rsc_parser import parse, RNode
import vcmx_import

LOCAL = Path(r'C:\Users\FinnStetter\OneDrive - Ximaj IT-Solutions GmbH\Dokumente\KUKA\iiQWorks.Sim 1.3\My Models\Untitled.vcmx')


def obj(name, scripts=(), signals=None, kind='box'):
    component = SceneObj(name, kind, obstacle=False)
    component.vc_data = {'scripts': list(scripts), 'signals': signals or {}, 'properties': {}}
    return component


def original_components():
    with zipfile.ZipFile(LOCAL) as archive:
        root = parse(archive.read('layout.rsc').decode('utf8', 'replace'))
    resources = [n for n in root.walk() if n.k == 'Node' and n.arg() == 'rSimResource']
    sensor = next(n for n in resources if n.name() == 'FarbSensor')
    block = next(n for n in resources if any('vc.vcColor' in s and 'random.choice' in s for s in vcmx_import._scripts(n)))
    display = next(n for n in resources if any('zylinder_faerben' in s for s in vcmx_import._scripts(n)))
    return block, sensor, display


class Runtime(unittest.TestCase):
    def test_typed_links_robot_ports_reentrancy_and_imports(self):
        sim = Simulation()
        source = obj('source', ['from vcScript import *\ncomp=getComponent()\ndef OnSignal(s):\n print(s.Name, s.Value)'],
                     {'text': {'kind': 'string', 'value': ''}, 'number': {'kind': 'int', 'value': 0}})
        target = obj('target', ['from vcScript import *\ncomp=getComponent()\ndef OnSignal(s):\n comp.findBehavior(s.Name).signal(s.Value)'],
                     copy.deepcopy(source.vc_data['signals']))
        forbidden = obj('forbidden', ['import os', 'from vcScript import *\ndef OnStart():\n getComponent().RootFeature.createFeature()\ndef OnSimulationUpdate(t):\n print("tick")'])
        sim.scene = [source, target, forbidden]
        sim.links = [{'src': ('source', 'text'), 'dst': ('target', 'text')},
                     {'src': ('source', 'number'), 'dst': ('target', 'number')},
                     {'src': (sim.active.name, 'Outputs_Port_3'), 'dst': ('source', 'number')},
                     {'src': ('target', 'number'), 'dst': (sim.active.name, 'Inputs_Port_4')}]
        sim.wire_links()
        sim.run_scripts = True
        sim.init_scripts()
        host = sim.script_host
        host.components['source'].signals['text'].signal('BLAU')
        self.assertEqual(host.components['target'].signals['text'].Value, 'BLAU')
        host.components['source'].signals['number'].signal(17)
        self.assertEqual(host.components['target'].signals['number'].Value, 17)
        self.assertTrue(sim.io.get_in(4))
        sim.io.set_out(3, True)
        sim._route_links()
        self.assertEqual(host.components['source'].signals['number'].Value, 1)
        host.start()
        host.running = False
        host.start()
        self.assertEqual(sum('RootFeature.createFeature wird' in line for line in sim.log), 1)
        self.assertTrue(any('Import os ist nicht erlaubt' in line for line in sim.log))
        host.update()
        self.assertTrue(any('forbidden: tick' in line for line in sim.log))
        added = SceneObj('new_native_part', 'workpiece', obstacle=False)
        sim.scene.append(added)
        sim.t += .05
        host.update()
        self.assertIn(added.name, host.components)
        self.assertFalse(any('Skriptfehler' in line for line in sim.log))

    def test_update_rate_seed_reset_and_serialization(self):
        sim = Simulation()
        component = obj('timer', ['import random\nfrom vcScript import *\ncomp=getComponent()\ndef OnStart():\n comp.findBehavior("value").signal(random.randint(1,10000))\ndef OnSimulationUpdate(t):\n print("update")'],
                        {'value': {'kind': 'int', 'value': 0}})
        sim.scene = [component]
        sim.run_scripts = True
        sim.init_scripts()
        sim.script_host.start()
        first = sim.script_host.components['timer'].signals['value'].Value
        sim.tick(.1)
        self.assertLessEqual(sum('timer: update' in x for x in sim.log), 2)
        saved = json.loads(json.dumps(sim.to_dict()))
        loaded = Simulation()
        loaded.from_dict(saved)
        self.assertTrue(loaded.run_scripts)
        self.assertIsNotNone(loaded.script_host)
        sim.reset_world()
        self.assertEqual(sim.script_host.components['timer'].signals['value'].Value, 0)
        sim.script_host.start()
        self.assertEqual(sim.script_host.components['timer'].signals['value'].Value, first)
        saved['run_scripts'] = False
        loaded.from_dict(saved)
        self.assertIsNone(loaded.script_host)
        self.assertFalse(loaded.scene[0].scripted)
        loaded.run_scripts = True
        loaded.scene = [SceneObj('signal_only_creator', 'spawner')]
        loaded.scene[0].product_templates = [{'signals': {}, 'scripts': [], 'properties': {}}]
        loaded.init_scripts()
        self.assertIsNone(loaded.script_host)

    def test_script_extraction_wraps_escapes_signature(self):
        raw = 'from vcScript import *\\n' + '\\\n' + 'def OnStart():\\n    print(\\"Hallo\\")\\n# Begin signature block\\ninvalid'
        node = RNode('Functionality', ['rPythonScript'], [RNode('VariableSpace', [], [
            RNode('Variable', [], [RNode('Name', ['"Script"']), RNode('Value', ['"' + raw + '"'])])])])
        scripts = vcmx_import._scripts(RNode('Node', ['rSimResource'], [node]))
        self.assertEqual(scripts, ['from vcScript import *\ndef OnStart():\n    print("Hallo")'])

    @unittest.skipUnless(LOCAL.exists(), 'Lokale Originalskripte fehlen')
    def test_original_scripts_colour_sensor_display_clone_and_reset(self):
        block_node, sensor_node, display_node = original_components()
        sim = Simulation()
        block = obj('part', kind='workpiece')
        block.graspable = True
        sensor = obj('sensor', kind='color_sensor')
        display = obj('display', kind='lamp')
        for component, node in ((block, block_node), (sensor, sensor_node), (display, display_node)):
            component.vc_data = vcmx_import._runtime_data(node)
        sim.scene = [block, sensor, display]
        sim.links = [{'src': ('sensor', color), 'dst': ('display', color)}
                     for color in ('ROT', 'GRUEN', 'BLAU', 'GELB', 'WEISS')]
        sim.wire_links()
        sim.run_scripts = True
        sim.init_scripts()
        host = sim.script_host
        initial_colour = block.color
        colour_name = host.components['part'].signals['Farbe'].Value
        self.assertIn(colour_name, ('ROT', 'GRUEN', 'BLAU', 'GELB', 'WEISS'))
        host.start()
        trigger = host.components['sensor'].signals['ColorTrigger']
        trigger.signal(True)
        self.assertEqual(host.components['sensor'].signals['ColorID'].Value,
                         ('ROT', 'GRUEN', 'BLAU', 'GELB', 'WEISS').index(colour_name) + 1)
        self.assertEqual(display.color, block.color)
        self.assertTrue(sensor.scripted and display.scripted)
        clone = obj('clone', kind='workpiece')
        clone._runtime_created = True
        sim.scene.append(clone)
        host.clone(clone, block.vc_data)
        self.assertTrue(host.components['clone'].signals['Farbe'].Value)
        self.assertNotEqual(clone.color, '#8a9bb8')
        host.remove(clone)
        self.assertNotIn('clone', host.components)
        sim.reset_world()
        self.assertEqual(block.color, initial_colour)
        self.assertEqual(display.color, '#8a9bb8')
        self.assertEqual(host.components['sensor'].signals['ColorID'].Value, 0)
        self.assertNotIn(clone, sim.scene)
        self.assertFalse(any('Skriptfehler' in x for x in sim.log))

    @unittest.skipUnless(LOCAL.exists(), 'Lokale Testdatei fehlt')
    def test_untitled_60_seconds(self):
        sim = Simulation()
        report = vcmx_import.import_file(sim, str(LOCAL), run_scripts=True)
        self.assertTrue(report['scripts'])
        self.assertTrue(any('/Produkt' in x['component'] for x in report['scripts']))
        sim.stop_on_collision = False
        sim.start()
        detected = 0
        host = sim.script_host
        sensor = next(c for c in host.Components if c.Name == 'FarbSensor')
        display = next(c for c in host.Components if any('zylinder_faerben' in s for s in c.data['scripts']))
        for _ in range(600):
            sim.tick(.1)
            self.assertFalse(any('Skriptfehler' in x or 'FEHLER:' in x for x in sim.log))
            if sensor.signals['ColorID'].Value:
                part = next(ns['finde_werkstueck']() for ns in sensor.scripts if 'finde_werkstueck' in ns)
                self.assertIsNotNone(part)
                self.assertEqual(display.obj.color, part.obj.color)
                detected += 1
        self.assertGreater(detected, 0)
        self.assertGreater(sim.stats['created'], 0)
        saved = sim.to_dict()
        self.assertTrue(saved['run_scripts'])
        self.assertTrue(any(o['product_templates'] for o in saved['scene'] if o['kind'] == 'spawner'))


if __name__ == '__main__':
    unittest.main()
