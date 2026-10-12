"""Detailmodelle der Katalogteile (part_geom): gueltige Netze, richtige Lage, Masse und Darstellungsliste."""
import os
import sys
import unittest
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'ximaj_robosim'))
import part_geom

CASES = [("conveyor", "", (1000, 300, 300)), ("conveyor", "", (1500, 400, 350)), ("conveyor", "", (3000, 500, 400)),
         ("conveyor", "roller", (2000, 600, 500)), ("fence", "", (2000, 20, 1800)), ("fence", "", (20, 4000, 1800)),
         ("sensor", "", (40, 300, 150)), ("color_sensor", "", (40, 300, 150)), ("lamp", "", (120, 120, 260)),
         ("spawner", "", (100, 100, 100)), ("sink", "", (400, 400, 300)), ("cylinder", "column", (300, 300, 2500)),
         ("box", "pallet", (1200, 800, 144)), ("box", "cabinet", (800, 600, 1900)), ("box", "table", (1200, 800, 800)),
         ("box", "gitterbox", (1200, 800, 900)), ("box", "shelf", (1500, 500, 2000)), ("box", "pedestal", (500, 500, 300)),
         ("box", "pedestal", (600, 600, 600)), ("box", "carton", (400, 300, 200)), ("workpiece", "carton", (400, 300, 200)),
         ("box", "fixture", (300, 300, 120))]
# Erlaubter Ueberstand ueber die Kollisionsmasse in mm (x, y, z unten, z oben)
OVER = {"conveyor": (12, 320, 0, 12), "fence": (90, 90, 0, 0), "sensor": (20, 90, 60, 0), "color_sensor": (20, 90, 60, 0)}


class PartGeomTests(unittest.TestCase):
    def check(self, kind, style, size, **p):
        meshes = part_geom.build(kind, style, size, **p)
        self.assertTrue(meshes, (kind, style, size))
        tris = 0
        for v, n, f, mat in meshes:
            self.assertIn(mat, part_geom.MATS)
            self.assertEqual((v.dtype, n.dtype, f.dtype), (np.float32, np.float32, np.uint32))
            self.assertEqual(v.shape, n.shape)
            self.assertEqual(f.shape[1], 3)
            self.assertTrue(np.isfinite(v).all() and np.isfinite(n).all())
            np.testing.assert_allclose(np.linalg.norm(n, axis=1), 1, atol=1e-4)
            self.assertLess(int(f.max()), len(v))
            cr = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]]).astype(float)
            self.assertTrue((np.linalg.norm(cr, axis=1) > 0).all(), (kind, style, mat, "entartet"))
            self.assertTrue((np.einsum("ij,ij->i", cr, n[f].sum(axis=1)) > 0).all(), (kind, style, mat, "Drehsinn"))
            tris += len(f)
        self.assertLess(tris, 60000, (kind, style))
        v = np.vstack([m[0] for m in meshes]).astype(float)
        L, W, H = size
        ox, oy, zlo, zhi = OVER.get(kind, (25, 30, 0, 12))
        lo = np.array([-L / 2 - ox, -W / 2 - oy, -zlo]) - 1.0
        hi = np.array([L / 2 + ox, W / 2 + oy, H + zhi]) + 1.0
        self.assertTrue((v.min(0) >= lo).all(), (kind, style, "unten", v.min(0), lo))
        self.assertTrue((v.max(0) <= hi).all(), (kind, style, "oben", v.max(0), hi))
        return meshes

    def test_catalog_parts(self):
        for kind, style, size in CASES:
            with self.subTest(kind=kind, style=style, size=size):
                self.check(kind, style, size)

    def test_other_sizes(self):
        for kind, style, size in CASES:
            for k in (0.6, 1.7):
                s = tuple(x * k for x in size)
                with self.subTest(kind=kind, style=style, size=s):
                    if part_geom.build(kind, style, s):
                        self.check(kind, style, s)

    def test_conveyor_options(self):
        for roller in (False, True):
            for feet in (0, 1, 3, 12):
                self.check("conveyor", "roller" if roller else "", (2000, 500, 400), feet=feet, roller=roller)
        # Gurt- und Rollenoberkante liegen auf H (Teile liegen dort auf)
        for style in ("", "roller"):
            v = np.vstack([m[0] for m in part_geom.build("conveyor", style, (2000, 500, 400)) if m[3] in ("belt", "metal")])
            v = v[np.abs(v[:, 1]) <= 250]
            self.assertAlmostEqual(float(v[:, 2].max()), 400.0, delta=0.5)

    def test_fallback_and_styles(self):
        self.assertEqual(part_geom.build("box", "", (100, 100, 100)), [])
        self.assertEqual(part_geom.build("box", "unbekannt", (100, 100, 100)), [])
        self.assertEqual(part_geom.build("zone", "", (100, 100, 100)), [])
        self.assertEqual(part_geom.build("conveyor", "", (10, 10, 10)), [])
        self.assertEqual(part_geom.build("fence", "", (float("nan"), 20, 1800)), [])
        for kind, entries in part_geom.STYLES.items():
            self.assertEqual(entries[0][0], "")
            for style, text in entries[1:]:
                self.assertTrue(text)
                self.assertTrue(part_geom.build(kind, style, (1200, 800, 900)), (kind, style))
        for kind, style, _ in CASES:                     # extreme Masse: schnell einfache Darstellung
            self.assertEqual(part_geom.build(kind, style, (1e9, 1e9, 1e9)), [])
        big = part_geom.build("box", "gitterbox", (20000, 20000, 20000))
        self.assertLessEqual(sum(len(m[2]) for m in big), part_geom.MAX_TRIS)
        p = part_geom.led_point("color_sensor", (40, 300, 150))
        self.assertTrue(150 < p[1] < 200 and 75 < p[2] < 150)


if __name__ == "__main__":
    unittest.main()
