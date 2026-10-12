"""Synthetischer, reproduzierbarer CPU-Test; keine Aussage über die GPU-Bildrate."""
from pathlib import Path
import json
import statistics
import sys
import time

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'ximaj_robosim'))
from sim import Simulation, SceneObj
from version import VERSION

s = Simulation()
s.scene = [SceneObj(f'Tisch{i}', pos=[(i % 20) * 750, (i // 20) * 750, 0], size=[600, 600, 300]) for i in range(250)]
s.scene += [SceneObj(f'Teil{i}', 'workpiece', pos=[(i % 20) * 750, (i // 20) * 750, 300],
                     size=[50, 50, 50], obstacle=False, graspable=True) for i in range(200)]
s.speed_factor = 1
s.world_paused = False
s._update_world(.01)
timings = []
for _ in range(12):
    before = time.perf_counter()
    s._update_world(.01)
    timings.append((time.perf_counter() - before) * 1000)
data = {'version': VERSION, 'fixture': 'synthetisch: 250 statische Auflagen, 200 Teile; kein GPU-Test',
        'steps': len(timings), 'median_world_ms': statistics.median(timings),
        'min_ms': min(timings), 'max_ms': max(timings), 'samples_ms': timings,
        'final_positions': [o.pos for o in s.scene if o.graspable]}
print(json.dumps(data, indent=2))
