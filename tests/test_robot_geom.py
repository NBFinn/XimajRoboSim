"""Robotergeometrie fuer alle Modelle pruefen (Vertrag von robot_geom.build_robot_meshes)."""
import sys, os
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'ximaj_robosim'))
import kinematics, robot_geom

MATS = {"body", "dark", "metal", "trim", "warn"}


def check(key, m):
    links = robot_geom.build_robot_meshes(m)
    assert len(links) == 7, (key, len(links))
    tris = 0
    for i, link in enumerate(links):
        assert link, f"{key}: Glied {i} leer"
        allv = []
        for v, n, f, mat in link:
            assert mat in MATS, (key, i, mat)
            assert v.dtype == np.float32 and n.dtype == np.float32 and f.dtype == np.uint32, (key, i)
            assert v.ndim == 2 and v.shape[1] == 3 and n.shape == v.shape and f.ndim == 2 and f.shape[1] == 3, (key, i)
            assert np.isfinite(v).all() and np.isfinite(n).all(), f"{key}: Glied {i} nicht endlich"
            assert np.abs(np.linalg.norm(n, axis=1) - 1).max() < 1e-3, f"{key}: Glied {i} Normalen nicht normiert"
            assert f.max() < len(v), (key, i)
            assert not ((f[:, 0] == f[:, 1]) | (f[:, 1] == f[:, 2]) | (f[:, 0] == f[:, 2])).any(), (key, i)
            tris += len(f)
            allv.append(v)
        V = np.vstack(allv)
        ext = V.max(0) - V.min(0)
        assert ext.max() < 1.5 * m.reach, f"{key}: Glied {i} zu gross {ext}"
        if i == 2:
            z0, z1 = V[:, 2].min(), V[:, 2].max()
            assert z0 <= 0.1 * m.a2 and z1 >= 0.9 * m.a2, f"{key}: Oberarm deckt 0..a2 nicht ab ({z0:.0f}..{z1:.0f})"
            assert z0 >= -0.6 * m.a2 and z1 <= 1.6 * m.a2, f"{key}: Oberarm zu lang ({z0:.0f}..{z1:.0f})"
        if i == 6:
            assert np.linalg.norm(V, axis=1).max() < 0.1 * m.reach, f"{key}: Flansch zu gross"
    assert tris <= 40000, f"{key}: {tris} Dreiecke"
    again = robot_geom.build_robot_meshes(m)
    for a, b in zip(links, again):
        for (v1, n1, f1, m1), (v2, n2, f2, m2) in zip(a, b):
            assert m1 == m2 and np.array_equal(v1, v2) and np.array_equal(f1, f2), f"{key}: nicht deterministisch"
    return tris


def main():
    for key, m in kinematics.MODELS.items():
        check(key, m)
    print(f"ok ({len(kinematics.MODELS)} Modelle)")


if __name__ == "__main__":
    main()
