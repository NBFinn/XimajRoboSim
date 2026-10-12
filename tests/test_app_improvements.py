"""Regression checks for import/start, WAIT, dock sizing and update feedback."""
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import urllib.error
import zipfile

ROOT = Path(os.environ.get('XRS_PROJECT', r'C:\Users\FinnStetter\Documents\XimajRoboSim'))
sys.path.insert(0, str(ROOT / 'ximaj_robosim'))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QApplication, QWidget
import main
import sim
import statements
import update
import vcmx_import


class LayoutViewer(QWidget):
    """Only replace the 3D canvas; use the real dock widgets and layouts."""
    picked = pyqtSignal(object)
    object_moved = pyqtSignal(object)
    target_picked = pyqtSignal(str, object)
    measured = pyqtSignal(dict)
    interacted = pyqtSignal(object)
    selection_changed = pyqtSignal(list)

    def __init__(self, simulation):
        super().__init__()
        self.selected = None
        self.center = [0, 0, 0]
        self.mode = 'select'
        self.move_children = True
        self.snap_step = 500.0
        self.snap_auto = True
        self.snap_always = True
        self.selection = []
        self.pts = []
        self.measure_result = None
        for attr in ('light_mode', 'shadows', 'show_trail', 'show_frames', 'show_reach', 'show_swept'):
            setattr(self, attr, False)


class Improvements(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_window(self):
        with patch.object(main, 'load_settings', return_value={'auto_update': False}), patch.object(main, 'Viewer', LayoutViewer):
            w = main.MainWindow()
        w.timer.stop()
        self.addCleanup(w.deleteLater)
        return w

    def test_import_keeps_helpers_and_switches_out_of_statements(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as d:
            path = Path(d) / 'fixture.vcmx'
            with zipfile.ZipFile(path, 'w') as z:
                z.writestr('fixture/KRC/R1/Program/main.src', 'DEF main()\nhelper()\nWAIT FOR $IN[5]\nEND')
                z.writestr('fixture/KRC/R1/Program/helper.src', 'DEF helper()\n$OUT[7]=TRUE\nEND')
            s = sim.Simulation()
            s.active.mode = 'statements'
            s.active.statements = [statements.new('HALT')]
            rep = vcmx_import.import_file(s, str(path))
            self.assertEqual(s.active.mode, 'xrl')
            self.assertEqual(s.src, rep['main_program'])
            self.assertIn('DEF helper()', s.src)
            s.start()
            s.tick(0.02)
            self.assertEqual(s.state, 'wait')
            self.assertTrue(s.io.get_out(7))
            self.assertIn('WAIT FOR $IN[5]', s.message)
            for _ in range(5):
                s.tick(0.02)
            self.assertEqual(s.state, 'wait')
            s.io.set_in(5, True)
            s.tick(0.02)
            self.assertEqual(s.state, 'idle')
            rep['config_prelude'] = 'DEFDAT CONFIG_PRELUDE\nDECL INT test=2\nENDDAT'
            chosen = vcmx_import.program_source(rep, 'program/helper')
            self.assertTrue(chosen.startswith('DEF helper()'))
            self.assertIn('DEF main()', chosen)
            self.assertIn('CONFIG_PRELUDE', chosen)

    def test_editor_import_survives_start(self):
        w = self.make_window()
        w.sim.active.mode = 'statements'
        w.sim.active.statements = [statements.new('HALT')]
        source = 'DEF imported()\n$OUT[8]=TRUE\nEND'
        w.use_imported_program(source)
        w.run_prog()
        w.sim.tick(0.02)
        self.assertEqual(w.sim.active.src, source)
        self.assertTrue(w.sim.io.get_out(8))
        self.assertEqual(w.sim.state, 'idle')

    def test_high_signal_can_release_imported_wait(self):
        w = self.make_window()
        w.use_imported_program('DEF imported()\nWAIT FOR $IN[119]\n$OUT[120]=TRUE\nEND')
        w.run_prog()
        w.sim.tick(0.02)
        self.assertEqual(w.sim.state, 'wait')
        w.io_bank.setCurrentIndex(1)
        self.assertEqual(w.io_t.item(54, 0).text(), 'IN[119]')
        w.io_t.item(54, 1).setText('Freigabe')
        w.io_t.item(54, 2).setCheckState(Qt.CheckState.Checked)
        self.assertTrue(w.sim.io.get_in(119))
        self.assertFalse(w.sim.io.get_in(55))
        self.assertEqual(w.sim.io.names[('in', 119)], 'Freigabe')
        w.sim.tick(0.02)
        self.assertEqual(w.sim.state, 'idle')
        self.assertTrue(w.sim.io.get_out(120))
        w.io_bank.setCurrentIndex(0)
        self.assertEqual(w.io_t.item(54, 1).text(), '')
        w.io_bank.setCurrentIndex(1)
        self.assertEqual(w.io_t.item(54, 1).text(), 'Freigabe')
        w.io_bank.setCurrentIndex(15)
        w.io_t.item(63, 2).setCheckState(Qt.CheckState.Checked)
        self.assertTrue(w.sim.io.get_in(1024))

    def test_docks_can_be_reduced(self):
        w = self.make_window()
        w.resize(1400, 800)
        w.show()
        self.app.processEvents()
        w.resizeDocks([w.dock_l, w.dock_r], [100, 100], Qt.Orientation.Horizontal)
        w.resizeDocks([w.dock_b], [80], Qt.Orientation.Vertical)
        self.app.processEvents()
        self.assertLessEqual(w.dock_l.width(), 130)
        self.assertLessEqual(w.dock_r.width(), 130)
        self.assertLessEqual(w.dock_b.height(), 100)
        self.assertIsNotNone(w.dock_l.widget().widget())
        w.hide()

    def test_manual_update_error_is_visible_and_clears_old_download(self):
        w = self.make_window()
        w.up_install.setEnabled(True)
        w.dock_b.hide()
        w.bottom.setCurrentIndex(0)
        with patch.object(main.upd, 'check', return_value={'error': 'Privates Repository', 'current': update.VERSION}):
            w.check_updates(False)
            deadline = time.monotonic() + 3
            while w._checking_updates and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(0.01)
        self.assertFalse(w._checking_updates)
        self.assertFalse(w.dock_b.isHidden())
        self.assertEqual(w.bottom.currentIndex(), 7)
        self.assertIn('Privates Repository', w.up_notes.toPlainText())
        self.assertFalse(w.up_install.isEnabled())
        self.assertTrue(w.up_btn.isEnabled())

    def test_update_thread_exception_returns_to_usable_ui(self):
        w = self.make_window()
        with patch.object(main.upd, 'check', side_effect=ValueError('Ungültige Release-Daten')):
            w.check_updates(False)
            deadline = time.monotonic() + 3
            while w._checking_updates and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(0.01)
        self.assertFalse(w._checking_updates)
        self.assertIn('Ungültige Release-Daten', w.up_notes.toPlainText())
        self.assertTrue(w.up_btn.isEnabled())

    def test_private_release_error_and_setup_preference(self):
        err = urllib.error.HTTPError(update.API, 404, 'not found', {}, None)
        with patch.object(update, '_get', side_effect=err):
            info = update.check()
        self.assertIn('GitHub-CLI-Anmeldung', info['error'])
        release = {'tag_name': 'v9.0.0', 'assets': [
            {'name': 'XimajRoboSim-9.0.0.zip', 'browser_download_url': 'https://test/zip'},
            {'name': 'XimajRoboSim-Setup-9.0.0.exe', 'browser_download_url': 'https://test/setup'},
            {'name': 'XimajRoboSim-Setup-9.0.0.exe.sha256', 'browser_download_url': 'https://test/sha'}]}
        with patch.object(update, '_get', return_value=io.BytesIO(json.dumps(release).encode())), patch.object(update, 'FROZEN', True):
            info = update.check()
        self.assertTrue(info['available'])
        self.assertEqual(info['kind'], 'setup')


if __name__ == '__main__':
    unittest.main(verbosity=2)
