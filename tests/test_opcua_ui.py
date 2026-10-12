"""Qt-Oberfläche mit isolierten Nutzerdaten und echtem lokalen OPC-UA-Server."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
ROOT = Path(__file__).resolve().parents[1]
profile = ROOT / 'test-temp' / 'ui-profile'
profile.mkdir(parents=True, exist_ok=True)
os.environ['APPDATA'] = str(profile)
sys.path.insert(0, str(ROOT / 'ximaj_robosim'))
from PyQt6.QtWidgets import QApplication, QLineEdit, QTableWidget, QPushButton
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFontDatabase, QFont
import main
import dialogs
import theme
from opcua_srv import OpcUaService
from kinematics import mat_to_pose


class UiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        QFontDatabase.addApplicationFont(r'C:\Windows\Fonts\segoeui.ttf')
        cls.app.setFont(QFont('Segoe UI', 10))
        cls.app.setStyleSheet(theme.stylesheet())
        main.load_settings = lambda: {'auto_update': False, 'opcua_local': True}
        cls.window = main.MainWindow()
        cls.window.timer.stop()
        cls.window.autosave_timer.stop()
        cls.window.teach_point()

    @classmethod
    def tearDownClass(cls):
        cls.window.opc.stop()
        cls.window._saved_snapshot = cls.window.history.current
        cls.window.deleteLater()
        cls.app.processEvents()

    def test_teach_preserves_reference_and_project_roundtrip(self):
        w = self.window
        w.sim.active.set_root([1000, 200, 0, 30, 0, 0])
        w.sim.active.base = [100, 0, 50, 0, 0, 0]
        w.sim.update_sv()
        w.teach_point()
        point = w.sim.waypoints[-1]
        self.assertEqual(point['base_world'], list(map(float, mat_to_pose(w.sim.base_world()))))
        self.assertEqual(point['e1'], w.sim.e1)
        from sim import Simulation
        other = Simulation()
        other.from_dict(w.sim.to_dict())
        self.assertEqual(other.waypoints[-1], point)

    def test_node_dialog_filter_copy_and_sizes(self):
        import socket
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0))
            port = s.getsockname()[1]
        service = OpcUaService(self.window.sim, port, local_only=True, n_io=16)
        self.assertTrue(service.start(), service.error)
        d = dialogs.opcua_nodes_dialog(self.window, service, run=False)
        try:
            table = d.findChild(QTableWidget, 'opcNodesTable')
            flt = d.findChild(QLineEdit, 'opcNodesFilter')
            self.assertGreater(table.rowCount(), 50)
            flt.setText('/Points/')
            self.assertGreater(table.rowCount(), 0)
            self.assertTrue(all('/Points/' in table.item(i, 0).text() for i in range(table.rowCount())))
            table.selectRow(0)
            b = next(b for b in d.findChildren(QPushButton) if b.text() == 'NodeId kopieren')
            b.click()
            self.assertEqual(self.app.clipboard().text(), table.item(0, 0).text())
            images = ROOT / 'test-results'
            images.mkdir(exist_ok=True)
            for width, height in ((640, 420), (960, 600), (1280, 720)):
                d.resize(width, height)
                d.show()
                self.app.processEvents()
                self.assertLessEqual(table.geometry().bottom(), d.height())
                self.assertGreater(table.viewport().width(), 100)
                self.assertGreater(table.viewport().height(), 50)
                self.assertTrue(d.grab().save(str(images / f'opcua-nodes-{width}.png')))
        finally:
            d.close()
            service.stop()

    def test_removed_robot_command_is_not_retargeted(self):
        w = self.window
        initial = w.sim.state
        w.opc.commands.append(('start', None, 'Entfernter Roboter'))
        w.process_opc_commands()
        self.assertEqual(w.sim.state, initial)

    def test_gripper_mapping_warning(self):
        w = self.window
        previous = list(w.sim.links)
        try:
            w.sim.links = [{'src': (w.sim.active.name, 'Outputs_Port_1'), 'dst': ('Teile-Erzeuger', 'CreationSignal')}]
            w.refresh_ui()
            self.assertIn('$OUT[1]', w.grip_status.text())
            self.assertIn('Teile-Erzeuger', w.grip_status.text())
        finally:
            w.sim.links = previous


if __name__ == '__main__':
    unittest.main(verbosity=2)
