"""Konservative Vorauswahl von Auflageflächen; schmale Prüfung bleibt im Simulationskern."""
import math
import numpy as np


class SupportIndex:
    def __init__(self, scene, cell=500.):
        self.cell = float(cell)
        self.buckets, self.wide = {}, []
        self.count = 0
        for o in scene:
            if o.attached or o.kind in ('sensor', 'color_sensor', 'lamp', 'spawner', 'sink', 'zone'):
                continue
            if not (o.obstacle or o.kind in ('conveyor', 'conveyor_arc')):
                continue
            self.count += 1
            # Die bestehende Auflageprüfung projiziert auf z=Objektboden: geneigte Flächen breit zulassen.
            if o.graspable or o.parent or o.kind == 'conveyor_arc' or abs(o.rot[1]) > 1e-9 or abs(o.rot[2]) > 1e-9:
                self.wide.append(o)
                continue
            half = np.abs(o.matrix()[:2, :2]) @ (np.asarray(o.size[:2], float) / 2)
            lo = np.floor((np.asarray(o.pos[:2]) - half - 1e-6) / self.cell).astype(int)
            hi = np.floor((np.asarray(o.pos[:2]) + half + 1e-6) / self.cell).astype(int)
            if int(hi[0] - lo[0] + 1) * int(hi[1] - lo[1] + 1) > 256:
                self.wide.append(o)
                continue
            for x in range(int(lo[0]), int(hi[0]) + 1):
                for y in range(int(lo[1]), int(hi[1]) + 1):
                    self.buckets.setdefault((x, y), []).append(o)

    def query(self, x, y):
        key = (math.floor(x / self.cell), math.floor(y / self.cell))
        return self.buckets.get(key, []) + self.wide
