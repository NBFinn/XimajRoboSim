import sys, os, glob
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'ximaj_robosim'))
from sim import Simulation
import vcmx_import
base = r"C:\Users\FinnStetter\OneDrive - Ximaj IT-Solutions GmbH\Dokumente\KUKA\iiQWorks.Sim 1.3\My Models"
for f in glob.glob(os.path.join(base, "**", "*.vcmx"), recursive=True):
    s = Simulation()
    r = vcmx_import.import_file(s, f)
    if not r["main_program"]:
        continue
    s.load_program(r["main_program"])
    s.stop_on_collision = False
    s.start()
    moves = 0
    last_line = None
    for i in range(60 * 120):
        s.tick(1 / 60)
        if s.motion is not None and s.cur_line != last_line:
            moves += 1
            last_line = s.cur_line
        if s.state in ("idle", "error", "stopped"):
            break
        if s.state == "wait" and s.wait_fn is not None and i > 600:
            break
    print(f"{os.path.basename(f):28s} Zustand={s.state:8s} t={s.t:6.1f}s Bewegungen={moves:3d} Zeile={s.cur_line} | {s.message[:90]}")
