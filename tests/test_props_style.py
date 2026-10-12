"""Eigenschaften mit echtem Qt/GL pruefen: python tests/test_props_style.py."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ximaj_robosim"))
from PyQt6.QtGui import QColor, QSurfaceFormat
from PyQt6.QtWidgets import QApplication, QColorDialog
from PyQt6.QtTest import QTest
import main
import part_geom
from sim import SceneObj, Simulation


class PropsStyleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fmt = QSurfaceFormat()
        fmt.setDepthBufferSize(24)
        fmt.setStencilBufferSize(8)
        QSurfaceFormat.setDefaultFormat(fmt)
        cls.app = QApplication.instance() or QApplication([])
        cls.tmp = tempfile.TemporaryDirectory(prefix="xrs_props_")
        cls.settings = patch.object(main, "load_settings", return_value={"auto_update": False})
        cls.save_settings = patch.object(main, "save_settings")
        cls.settings.start()
        cls.save_settings.start()
        cls.w = main.MainWindow()
        cls.w.autosave.directory = Path(cls.tmp.name)
        cls.w.show()
        QTest.qWait(400)

    @classmethod
    def tearDownClass(cls):
        cls.w._saved_snapshot = cls.w.history.current
        cls.w.close()
        cls.app.quit()
        cls.save_settings.stop()
        cls.settings.stop()
        cls.tmp.cleanup()

    def setUp(self):
        self.w.sim.scene.clear()
        self.w.refresh_scene_list()
        self.w.add_obj("box")
        self.w.add_obj("conveyor")
        self.w.sim.scene.append(SceneObj("Kurvenband", "conveyor_arc"))
        self.w.sim.scene.append(SceneObj("Sensor", "sensor"))
        self.w.refresh_scene_list()
        self.w._clean_history()

    def select(self, index):
        self.w.obj_list.setCurrentRow(index)
        return self.w.sim.scene[index]

    def check_undo_redo(self, index, field, before, after, change):
        self.select(index)
        states = len(self.w.history._states)
        change()
        self.assertEqual(getattr(self.w.sim.scene[index], field), after)
        self.assertEqual(len(self.w.history._states), states + 1)
        self.w.undo()
        self.assertEqual(getattr(self.w.sim.scene[index], field), before)
        self.w.redo()
        self.assertEqual(getattr(self.w.sim.scene[index], field), after)

    def test_styles_and_roundtrip(self):
        for index in (0, 1):
            obj = self.select(index)
            styles = part_geom.STYLES[obj.kind]
            self.assertEqual([(self.w.p_style.itemData(i), self.w.p_style.itemText(i))
                              for i in range(self.w.p_style.count())], styles)
            self.check_undo_redo(index, "style", "", styles[1][0],
                                 lambda: self.w.p_style.setCurrentIndex(1))
        loaded = Simulation()
        loaded.from_dict(json.loads(json.dumps(self.w.sim.to_dict())))
        self.assertEqual([o.style for o in loaded.scene], [o.style for o in self.w.sim.scene])
        self.select(0)
        self.w.p_style.setCurrentIndex(0)
        self.assertEqual(self.w.sim.scene[0].style, "")

    def test_conveyor_colors(self):
        for index in (1, 2):
            for field, button, color in (("frame_color", self.w.p_frame_color, "#123456"),
                                         ("belt_color", self.w.p_belt_color, "#abcdef")):
                before = getattr(self.w.sim.scene[index], field)
                with patch.object(QColorDialog, "getColor", return_value=QColor(color)) as dialog:
                    self.check_undo_redo(index, field, before, color, button.click)
                    dialog.assert_called_once()

    def test_feet_bounds_and_undo(self):
        self.assertEqual((self.w.p_feet.minimum(), self.w.p_feet.maximum()), (0, 20))
        for index in (1, 2):
            for value in (0, 20):
                before = self.w.sim.scene[index].feet
                self.check_undo_redo(index, "feet", before, value,
                                     lambda: self.w.p_feet.setValue(value))

    def test_selection_does_not_change_history(self):
        snapshot = self.w.history.current
        for index in (0, 1, 2, 3, 0, 1):
            obj = self.select(index)
            self.assertEqual(self.w.history.current, snapshot)
            self.assertEqual(self.w.p_style.isHidden(), obj.kind not in part_geom.STYLES)
            for widget in (self.w.p_frame_color, self.w.p_belt_color,
                           self.w.p_feet, self.w.p_feet_label):
                self.assertEqual(widget.isHidden(), obj.kind not in ("conveyor", "conveyor_arc"))
            if obj.kind in part_geom.STYLES:
                self.assertEqual(self.w.p_style.currentData(), obj.style)
            self.assertEqual(self.w.p_feet.value(), obj.feet)
        self.w.obj_list.setCurrentRow(-1)
        self.assertTrue(self.w.p_style.isHidden())
        self.assertTrue(self.w.p_feet.isHidden())
        self.assertEqual(self.w.history.current, snapshot)

    def test_cancel_color_has_no_undo_step(self):
        self.select(1)
        snapshot = self.w.history.current
        with patch.object(QColorDialog, "getColor", return_value=QColor()):
            self.w.p_frame_color.click()
            self.w.p_belt_color.click()
        self.assertEqual(self.w.history.current, snapshot)
        self.assertFalse(self.w.history.can_undo)


if __name__ == "__main__":
    unittest.main()
