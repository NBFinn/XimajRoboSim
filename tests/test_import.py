import sys, os, glob
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'ximaj_robosim'))
from sim import Simulation
import vcmx_import, xrl
base = r"C:\Users\FinnStetter\OneDrive - Ximaj IT-Solutions GmbH\Dokumente\KUKA\iiQWorks.Sim 1.3\My Models"
files = glob.glob(os.path.join(base, "**", "*.vcmx"), recursive=True)
if len(sys.argv) > 1:
    files = [f for f in files if sys.argv[1].lower() in f.lower()]
for f in files:
    s = Simulation()
    try:
        r = vcmx_import.import_file(s, f)
    except Exception as e:
        import traceback; traceback.print_exc(); continue
    print("=" * 70)
    print("\n".join(r["log"][:14]))
    print("Szene:", [(o.name, o.kind, [round(x) for x in o.size]) for o in s.scene][:6])
    if r["main_program"]:
        try:
            it = xrl.Interp(r["main_program"], s.io, s.sv, s.frame_tables())
            print("Parser-Hinweise:", len(it.warnings), it.warnings[:5])
            print("DEFs:", list(it.defs)[:10])
        except Exception as e:
            print("PARSE-FEHLER", e)
