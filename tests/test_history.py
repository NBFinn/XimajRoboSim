"""History, crash recovery and unsaved-project regression checks."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ximaj_robosim'))
from history import History, Autosave
from sim import Simulation, SceneObj


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.sim = Simulation()
        self.history = History(self.sim, limit=2)

    def add(self, name):
        self.sim.scene.append(SceneObj(name))
        self.history.snapshot()

    def test_duplicates_branch_and_limit(self):
        self.assertFalse(self.history.snapshot())
        for name in ('a', 'b', 'c'):
            self.add(name)
        self.assertTrue(self.history.undo())
        self.assertTrue(self.history.undo())
        self.assertFalse(self.history.undo())
        self.assertEqual([o.name for o in self.sim.scene], ['a'])
        self.assertTrue(self.history.redo())
        self.add('d')
        self.assertFalse(self.history.can_redo)

    def test_deep_snapshot_robot_program_and_runtime(self):
        self.add('a')
        self.sim.scene[0].pos[0] = 500
        self.sim.src = 'DEF TEST()\nEND'
        self.sim.add_robot()
        self.history.snapshot()
        self.sim.t = 42
        self.sim.scene[0].spawned = 9
        self.assertTrue(self.history.undo())
        self.assertEqual(len(self.sim.robots), 1)
        self.assertEqual(self.sim.scene[0].pos[0], 0)
        self.assertEqual(self.sim.scene[0].spawned, 0)
        self.assertEqual(self.sim.t, 0)
        self.assertTrue(self.history.redo())
        self.assertEqual(len(self.sim.robots), 2)
        self.assertIn('TEST', self.sim.robots[0].src)
        self.assertEqual(self.sim.scene[0].pos[0], 500)

    def test_busy_robot_blocks_history(self):
        self.add('a')
        for state in ('running', 'wait', 'stopping', 'paused'):
            self.sim.active.state = state
            self.assertFalse(self.history.snapshot())
            self.assertFalse(self.history.can_undo)
            self.assertFalse(self.history.undo())
        self.sim.active.state = 'idle'
        self.assertTrue(self.history.undo())


class AutosaveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, APPDATA=self.tmp.name)
        env.start()
        self.addCleanup(env.stop)
        self.backup = Autosave()
        self.state = History(Simulation()).current

    def test_rotation_atomic_write_and_clear(self):
        for _ in range(7):
            self.backup.write(self.state)
        self.assertEqual(len(self.backup.files()), 5)
        self.assertFalse(list(self.backup.directory.glob('*.tmp')))
        self.assertEqual(self.backup.candidates()[0][1]['project'], json.loads(self.state))
        self.backup.clear()
        self.assertEqual(self.backup.files(), [])

    def test_newer_than_saved_and_project_isolation(self):
        project = Path(self.tmp.name) / 'project.xrsim'
        project.write_text(self.state, encoding='utf8')
        backup = self.backup.write(self.state, str(project))
        older = project.stat().st_mtime_ns - 1000000
        os.utime(backup, ns=(older, older))
        self.assertEqual(self.backup.candidates(), [])
        newer = project.stat().st_mtime_ns + 1000000
        os.utime(backup, ns=(newer, newer))
        self.assertEqual(len(self.backup.candidates()), 1)
        self.backup.write(self.state)
        self.backup.clear(str(project))
        self.assertEqual(len(self.backup.files()), 1)

    def test_corrupt_backup_is_ignored(self):
        self.backup.directory.mkdir(parents=True)
        (self.backup.directory / 'corrupt.json').write_text('{', encoding='utf8')
        self.assertEqual(self.backup.candidates(), [])


class WindowHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.env = patch.dict(os.environ, APPDATA=cls.tmp.name)
        cls.env.start()
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])
        import main
        cls.main = main

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()
        cls.tmp.cleanup()

    def setUp(self):
        with patch.object(self.main, 'load_settings', return_value={'auto_update': False}), \
                patch.object(self.main.catalog, 'load_user_catalog'):
            self.win = self.main.MainWindow()
        self.win.timer.stop()
        self.win.autosave_timer.stop()
        self.win.ribbon._atimer.stop()
        self.addCleanup(self.cleanup_window)

    def cleanup_window(self):
        self.win._saved_snapshot = self.win.history.current
        self.win.close()

    def test_edit_undo_redo_and_saved_title(self):
        w = self.win
        count = len(w.sim.scene)
        w.add_obj('box')
        self.assertTrue(w.dirty)
        self.assertTrue(w.windowTitle().endswith('*'))
        self.assertTrue(w.ribbon.undo_button.isEnabled())
        w.undo()
        self.assertEqual(len(w.sim.scene), count)
        self.assertFalse(w.dirty)
        self.assertTrue(w.ribbon.redo_button.isEnabled())
        w.redo()
        w.project_path = str(Path(self.tmp.name) / 'saved.xrsim')
        w._autosave()
        self.assertTrue(w.autosave.files())
        self.assertTrue(w.save_project())
        self.assertFalse(w.dirty)
        self.assertFalse(w.autosave.files())

    def test_program_and_properties_are_tracked(self):
        w = self.win
        source = w.editor.toPlainText()
        w.editor.setPlainText('DEF EDIT()\nEND')
        w.undo()
        self.assertEqual(w.editor.toPlainText(), source)
        w.add_obj('box')
        w.p_pos[0].setValue(123)
        self.assertEqual(w.sim.scene[-1].pos[0], 123)
        w.undo()
        self.assertEqual(w.sim.scene[-1].pos[0], 700)

    def test_qt_signal_arguments_are_ignored_by_zero_argument_slots(self):
        w = self.win
        count = len(w.sim.waypoints)
        button = w._btn('Punkt einlernen', w.teach_point)
        button.click()
        self.assertEqual(len(w.sim.waypoints), count + 1)
        self.assertTrue(w.dirty)

    def test_recovery_restores_dirty_project(self):
        w = self.win
        w.add_obj('box')
        count = len(w.sim.scene)
        w._autosave()
        w.undo()
        from PyQt6.QtWidgets import QMessageBox
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
            w._recover_autosave()
        self.assertEqual(len(w.sim.scene), count)
        self.assertTrue(w.dirty)

    def test_cancel_close_and_cancel_save_keep_backup(self):
        from PyQt6.QtWidgets import QMessageBox, QFileDialog
        from PyQt6.QtGui import QCloseEvent
        w = self.win
        w.add_obj('box')
        w._autosave()
        event = QCloseEvent()
        with patch.object(QMessageBox, 'exec', return_value=0):
            w.closeEvent(event)
        self.assertFalse(event.isAccepted())
        self.assertTrue(w.autosave.files())
        with patch.object(QFileDialog, 'getSaveFileName', return_value=('', '')):
            self.assertFalse(w.save_project())
        self.assertTrue(w.dirty)

    def test_gizmo_mirror_origin_and_paste(self):
        w = self.win
        w.add_obj('box')
        obj = w.sim.scene[-1]
        obj.pos[0] = 900
        w.ribbon._on_moved(obj)
        w.undo()
        self.assertEqual(w.sim.scene[-1].pos[0], 700)
        w.viewer.selected = w.sim.scene[-1]
        w.viewer.selection = [w.viewer.selected]
        w.ribbon.copy()
        count = len(w.sim.scene)
        w.ribbon.paste()
        w.undo()
        self.assertEqual(len(w.sim.scene), count)
        w.viewer.selected = w.sim.scene[-1]
        w.viewer.selection = [w.viewer.selected]
        w.ribbon.mirror(0)
        self.assertEqual(w.sim.scene[-1].mesh_mirror, [0])
        w.undo()
        self.assertEqual(w.sim.scene[-1].kind, 'box')

    def test_startup_open_preserves_untitled_recovery(self):
        w = self.win
        backup = w.autosave.write(w.history.current)
        project = Path(self.tmp.name) / 'startup.xrsim'
        project.write_text(w.history.current, encoding='utf8')
        w.open_project(str(project))
        self.assertTrue(backup.exists())
        self.assertFalse(w.dirty)

    def test_close_discard_and_save_cancel(self):
        from PyQt6.QtWidgets import QMessageBox, QFileDialog
        from PyQt6.QtGui import QCloseEvent
        w = self.win
        w.add_obj('box')
        selected = [None]

        def choose(box, role):
            selected[0] = next(b for b in box.buttons() if box.buttonRole(b) == role)
            return 0

        with patch.object(QMessageBox, 'exec', lambda box: choose(box, QMessageBox.ButtonRole.AcceptRole)), \
                patch.object(QMessageBox, 'clickedButton', lambda box: selected[0]), \
                patch.object(QFileDialog, 'getSaveFileName', return_value=('', '')):
            event = QCloseEvent()
            w.closeEvent(event)
            self.assertFalse(event.isAccepted())
        w._autosave()
        with patch.object(QMessageBox, 'exec', lambda box: choose(box, QMessageBox.ButtonRole.DestructiveRole)), \
                patch.object(QMessageBox, 'clickedButton', lambda box: selected[0]):
            event = QCloseEvent()
            w.closeEvent(event)
            self.assertTrue(event.isAccepted())
            self.assertFalse(w.autosave.files())

    def test_failed_save_keeps_dirty_and_backup(self):
        from PyQt6.QtWidgets import QMessageBox
        w = self.win
        w.add_obj('box')
        w.project_path = str(Path(self.tmp.name) / 'missing' / 'project.xrsim')
        w._autosave()
        with patch.object(QMessageBox, 'warning'):
            self.assertFalse(w.save_project())
        self.assertTrue(w.dirty)
        self.assertTrue(w.autosave.files())


if __name__ == '__main__':
    unittest.main()
