"""Qt-Bedienabläufe im Offscreen-Modus. 3D-Canvas ist ausdrücklich ein Layout-Platzhalter."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ximaj_robosim'))
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtWidgets import QDialog, QListWidget, QLineEdit, QMessageBox
import test_app_improvements as existing
from opcua_client import ClientLink
import main
import theme
import upgrade_ui


class UpgradeUI(unittest.TestCase):
    setUpClass = classmethod(existing.Improvements.setUpClass.__func__)
    make_window = existing.Improvements.make_window

    def test_failed_load_preserves_existing_cell_and_success_is_paused(self):
        w = self.make_window()
        before = w.sim.to_dict()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'bad.xrsim'
            p.write_text('{broken', encoding='utf-8')
            with patch.object(w, '_confirm_discard', return_value=True), patch.object(QMessageBox, 'warning') as warning:
                self.assertFalse(w.open_project(str(p)))
                self.assertTrue(warning.called)
            self.assertEqual(w.sim.to_dict(), before)
            p.write_text(json.dumps(before), encoding='utf-8')
            with patch.object(w, '_confirm_discard', return_value=True):
                w.open_project(str(p))
            self.assertEqual(w.sim.to_dict(), before)
            self.assertTrue(w.sim.world_paused)
            self.assertIs(w.sim.active.w, w.sim)
            w.sim.start()
            self.assertFalse(w.sim.world_paused)

    def test_search_preserves_scene_indices_and_preflight_rejects_invalid_cell(self):
        w = self.make_window()
        w.scene_search.setText('this name is absent')
        w.refresh_scene_list()
        self.assertTrue(all(w.obj_list.item(i).isHidden() for i in range(w.obj_list.count())))
        w.scene_search.clear()
        self.assertFalse(w.obj_list.item(0).isHidden())
        w.sim.pause_all()
        w.sim.scene[1].name = w.sim.scene[0].name
        w.run_prog()
        self.assertFalse(w.sim.any_busy())
        self.assertTrue(w.sim.world_paused)
        self.assertEqual(w.bottom.currentIndex(), w.cockpit_index)

    def test_command_query_never_executes_without_selection(self):
        w = self.make_window()
        clicked = []
        for page in w.ribbon.rb.pages.values():
            for group in page.groups.values():
                for button in group.items.values():
                    if hasattr(button, 'clicked'):
                        button.clicked.connect(lambda: clicked.append(True))
        def inspect_dialog():
            d = next(x for x in self.app.topLevelWidgets() if isinstance(x, QDialog) and x.windowTitle().startswith('Befehl'))
            self.assertGreater(d.findChild(QListWidget).count(), 0)
            self.assertEqual(clicked, [])
            d.reject()
        QTimer.singleShot(20, inspect_dialog)
        upgrade_ui.command_palette(w, 'Start')
        self.assertEqual(clicked, [])

    def test_new_project_removes_previous_connection_and_links(self):
        w = self.make_window()
        w.opc_clients = [ClientLink(w.sim)]
        w.sim.links = [dict(src=('unused', 'test'), dst=('unused', 'test'))]
        w.sim.run_scripts = True
        w.sim.active.breakpoints = {3}
        with patch.object(w, '_confirm_discard', return_value=True):
            w.new_project()
        self.assertEqual(w.opc_clients, [])
        self.assertEqual(w.sim.links, [])
        self.assertFalse(w.sim.run_scripts)
        self.assertFalse(w.sim.active.breakpoints)

    def test_widgets_at_window_sizes_and_debugger_gutter(self):
        for filename in ('segoeui.ttf', 'consola.ttf'):
            QFontDatabase.addApplicationFont('C:/Windows/Fonts/' + filename)
        self.app.setFont(QFont('Segoe UI', 9))
        self.app.setStyleSheet(theme.stylesheet())
        w = self.make_window()
        w.dock_l.hide()
        w.dock_r.hide()
        w.viewer.setStyleSheet('background:#081733')
        from PyQt6.QtWidgets import QLabel, QVBoxLayout
        QVBoxLayout(w.viewer).addWidget(QLabel('Offscreen-Layoutprüfung · 3D-Canvas als Platzhalter'))
        out = Path(__file__).resolve().parents[1] / 'test-results' / 'layout'
        out.mkdir(parents=True, exist_ok=True)
        for width, height in [(640, 600), (960, 720), (1280, 900)]:
            w.resize(width, height)
            w.show()
            self.app.processEvents()
            self.assertEqual(w.width(), width)
            self.assertEqual(w.ribbon.rb.compact_tabs.isVisible(), width < 1100)
            if width < 1100:
                w.ribbon.rb.compact_tabs.setCurrentText('PROGRAMM')
                self.assertEqual(w.ribbon.rb.current(), 'PROGRAMM')
            for index, label in [(w.cockpit_index, 'cockpit'), (w.debugger_index, 'debugger'), (1, 'editor')]:
                w.bottom.setCurrentIndex(index)
                w.resizeDocks([w.dock_b], [int(height * .65)], Qt.Orientation.Vertical)
                w.editor.toggle(3)
                w.refresh_ui()
                w.cockpit.refresh()
                w.debugger.refresh()
                self.app.processEvents()
                self.assertLessEqual(w.bottom.width(), width)
                self.assertGreater(w.bottom.currentWidget().height(), 60)
                self.assertTrue(w.grab().save(str(out / f'{label}-{width}.png')))
        w.hide()


if __name__ == '__main__':
    unittest.main(verbosity=2)
