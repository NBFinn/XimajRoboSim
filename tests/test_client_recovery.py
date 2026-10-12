"""Echter Loopback-Server: mehrere Zuordnungen, Abbruch, Wiederverbinden, Schreibfreigabe."""
import socket
import sys
from pathlib import Path
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ximaj_robosim'))
from sim import Simulation
from opcua_srv import OpcUaService
from opcua_client import ClientLink
from opcua_nodes import ROOT_ID, NAMESPACE_URI


def eventually(fn, timeout=12):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if fn():
            return True
        time.sleep(.025)
    return False


class Recovery(unittest.TestCase):
    def test_real_disconnect_reconnect_requires_write_rearm(self):
        plc, sim = Simulation(), Simulation()
        with socket.socket() as socket_:
            socket_.bind(('127.0.0.1', 0))
            port = socket_.getsockname()[1]
        service = OpcUaService(plc, port, local_only=True, n_io=16)
        self.assertTrue(service.start(), service.error)
        self.addCleanup(service.stop)
        nid = lambda tail: f'nsu={NAMESPACE_URI};s={ROOT_ID}/IO/{tail}'
        link = ClientLink(sim, service.endpoints()[0], mappings=[
            dict(node=nid('Out/O9'), dir='read', target='IN:20'),
            dict(node=nid('Out/O9'), dir='read', target='IN:21'),
            dict(node=nid('In/I11'), dir='write', target='OUT:12')], period=.04)
        self.addCleanup(link.disconnect)
        started = time.monotonic()
        self.assertTrue(link.connect(wait=False))
        self.assertLess(time.monotonic() - started, .2)
        worker = link.thread
        self.assertTrue(link.connect(wait=False))
        self.assertIs(link.thread, worker)
        self.assertTrue(eventually(lambda: link.connected), link.error)
        plc.io.set_out(9, True)
        sim.io.set_out(12, True)
        self.assertTrue(eventually(lambda: sim.io.get_in(20) and sim.io.get_in(21) and plc.io.get_in(11)),
                        str(link.mappings))
        service.stop()
        self.assertTrue(eventually(lambda: link.reconnects > 0 and not link.connected), link.status)
        self.assertFalse(link.writes_armed)
        # Neustart derselben realen Serverimplementierung am gleichen Port.
        plc.io.set_in(11, False)
        plc.io.set_out(9, False)
        self.assertTrue(service.start(), service.error)
        self.assertEqual(service.port, port)
        self.assertTrue(eventually(lambda: link.connected and not sim.io.get_in(20) and not sim.io.get_in(21)), link.error)
        time.sleep(.3)
        self.assertFalse(plc.io.get_in(11), 'Kein automatischer Schreibzugriff nach Wiederverbinden')
        self.assertTrue(link.mappings[2].get('error'))
        link.arm_writes()
        self.assertTrue(eventually(lambda: plc.io.get_in(11)))
        self.assertTrue(eventually(lambda: not any(m.get('error') for m in link.mappings)))
        self.assertNotIn('password', link.to_dict())


if __name__ == '__main__':
    unittest.main(verbosity=2)
