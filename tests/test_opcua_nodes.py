"""Echte Loopback-Verbindungen: feste NodeIds, Roboterkoordinaten und Teach-Punkte."""
import asyncio
import csv
import json
import math
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ximaj_robosim'))
from asyncua import Client, ua
from sim import Simulation, SceneObj
from opcua_srv import OpcUaService
from opcua_nodes import ROOT_ID, NAMESPACE_URI, child_id, export_nodes
from kinematics import mat_to_pose, pose_to_mat


class ExportTests(unittest.TestCase):
    def test_names_do_not_alias_paths(self):
        self.assertNotEqual(child_id('r', 'A/B'), child_id(child_id('r', 'A'), 'B'))
        self.assertNotEqual(child_id('r', 'A%2FB'), child_id('r', 'A/B'))

    def test_unknown_values_export_as_null(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'nodes.json'
            row = {'identifier': 'x', 'value': [float('nan'), 1.0]}
            export_nodes(p, [row], ['opc.tcp://localhost:4840'])
            data = json.loads(p.read_text(encoding='utf-8'))
            self.assertEqual(data['nodes'][0]['value'], [None, 1.0])
            export_nodes(p.with_suffix('.csv'), [row], [])
            with p.with_suffix('.csv').open(encoding='utf-8-sig') as f:
                rows = list(csv.DictReader(f, delimiter=';'))
            self.assertEqual(json.loads(rows[0]['value']), [None, 1.0])

    def test_failed_export_keeps_previous_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'nodes.json'
            p.write_text('vorher', encoding='utf-8')
            with self.assertRaises(TypeError):
                export_nodes(p, [{'value': object()}], [])
            self.assertEqual(p.read_text(encoding='utf-8'), 'vorher')
            self.assertEqual(len(list(Path(d).iterdir())), 1)


class RobotNodesTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_robot_nodes_and_restart(self):
        sim = Simulation()
        r = sim.active
        r.name = 'Roboter / A%'
        r.set_root([1200, -300, 0, 30, 0, 0])
        r.base = [100, 20, 50, 10, 0, 0]
        base = list(map(float, mat_to_pose(r.base_world())))
        r.waypoints = [dict(name='P/1', pos=[10, 20, 30, 40, 50, 60], S=2, T=3, base_world=base, e1=25.0),
                       dict(name='Alt', pos=[1, 2, 3, 4, 5, 6], S=0, T=0),
                       dict(name='P/1', pos=[70, 80, 90, 0, 0, 0], S=0, T=0)]
        sim.add_robot(None, [2500, 0, 0, 0, 0, 0], 'Zweiter')
        sock = socket.socket()
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
        sock.close()
        srv = OpcUaService(sim, port, local_only=True, n_io=16)
        self.assertTrue(srv.start(), srv.error)
        url = f'opc.tcp://127.0.0.1:{srv.port}/ximaj/robosim'
        prefix = child_id(ROOT_ID + '/Robots', r.name)
        try:
            async with Client(url) as c:
                idx = await c.get_namespace_index(NAMESPACE_URI)
                def node(path):
                    return c.get_node(ua.NodeId(path, idx))
                first_ids = {x['identifier']: x['node_id'] for x in srv.catalog()}
                self.assertTrue(all(';s=' in nid for nid in first_ids.values()))
                self.assertEqual(await node(prefix + '/PointCount').read_value(), 3)
                self.assertEqual(await node(prefix + '/Axes/A1').read_data_type_as_variant_type(), ua.VariantType.Double)
                axes = await node(prefix + '/Axes/JointPosition').read_value()
                self.assertEqual(axes, list(r.q))
                self.assertEqual(await node(prefix + '/Gripper/SignalIndex').read_value(), r.tool.grip_out)
                self.assertFalse(await node(prefix + '/Gripper/Holding').read_value())
                tcp = await node(prefix + '/Tcp/Pose').read_value()
                world = await node(prefix + '/TcpWorld/Pose').read_value()
                for a, b in zip(tcp, mat_to_pose(r.tcp_in_base())):
                    self.assertAlmostEqual(a, b)
                for a, b in zip(world, mat_to_pose(r.tcp_world())):
                    self.assertAlmostEqual(a, b)
                self.assertNotEqual(tcp, world)
                point = child_id(prefix + '/Points', 'P/1')
                self.assertEqual(await node(point + '/Pose').read_value(), [10, 20, 30, 40, 50, 60])
                self.assertTrue(await node(point + '/WorldKnown').read_value())
                expected = mat_to_pose(pose_to_mat(*base) @ pose_to_mat(10, 20, 30, 40, 50, 60))
                for a, b in zip(await node(point + '/WorldPose').read_value(), expected):
                    self.assertAlmostEqual(a, b)
                self.assertEqual(await node(point + '/E1').read_value(), 25.0)
                self.assertFalse(await node(prefix + '/Points/Alt/WorldKnown').read_value())
                self.assertTrue(all(math.isnan(x) for x in await node(prefix + '/Points/Alt/WorldPose').read_value()))
                self.assertEqual(await node(point + '/Duplicate/2/X').read_value(), 70.0)
                with self.assertRaises(ua.UaStatusCodeError):
                    await node(prefix + '/Tcp/X').write_value(123.0)
                r.q[0] += 5.0
                r.set_root([5000, 0, 0, 0, 0, 0])
                await asyncio.sleep(.2)
                # Teach-Weltbezug bleibt der gespeicherte Bezug beim Einlernen.
                for a, b in zip(await node(point + '/WorldPose').read_value(), expected):
                    self.assertAlmostEqual(a, b)
                r.waypoints[0]['pos'][0] = 111.0
                await asyncio.sleep(.3)
                self.assertAlmostEqual(await node(prefix + '/Axes/A1').read_value(), r.q[0])
                self.assertEqual(await node(point + '/X').read_value(), 111.0)
                await node(ROOT_ID + '/IO/In/I7').write_value(True)
                await asyncio.sleep(.2)
                self.assertTrue(sim.io.get_in(7))
                await node(prefix).call_method(ua.NodeId(prefix + '/Start', idx))
                self.assertIn(('start', None, r.name), srv.commands)
                del r.waypoints[1:]
                sim.robots.pop()
                await asyncio.sleep(.3)
                self.assertEqual(await node(prefix + '/PointCount').read_value(), 1)
                with self.assertRaises(ua.UaStatusCodeError):
                    await node(prefix + '/Points/Alt/X').read_value()
                with self.assertRaises(ua.UaStatusCodeError):
                    await node(ROOT_ID + '/Robots/Zweiter/State').read_value()
                self.assertFalse(any('/Points/Alt/' in x['identifier'] for x in srv.catalog()))
                self.assertEqual(srv.error, '')
            srv.stop()
            sim.scene.append(SceneObj('Band', 'conveyor'))
            self.assertTrue(srv.start(), srv.error)
            restarted = {x['identifier']: x['node_id'] for x in srv.catalog()}
            for identifier in (prefix + '/Axes/A1', point + '/X', ROOT_ID + '/Robot/Tcp/Pose'):
                self.assertEqual(first_ids[identifier], restarted[identifier])
            with tempfile.TemporaryDirectory() as d:
                export_nodes(Path(d) / 'nodes.json', srv.catalog(), srv.endpoints())
                json.loads((Path(d) / 'nodes.json').read_text(encoding='utf-8'))
        finally:
            srv.stop()


if __name__ == '__main__':
    unittest.main(verbosity=2)
