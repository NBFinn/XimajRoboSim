import sys, time, os, tempfile
import cascadio, trimesh
p = sys.argv[1]
t0 = time.time()
out = os.path.join(tempfile.gettempdir(), "xrs_step_test.glb")
cascadio.step_to_glb(p, out, 0.5, 0.5)
t1 = time.time()
sc = trimesh.load(out, force="scene")
m = sc.dump(concatenate=True) if hasattr(sc, "dump") else sc
print(f"STEP->GLB {t1 - t0:.1f}s, Geometrien: {len(getattr(sc, 'geometry', {}))}, Dreiecke: {len(m.faces)}, "
      f"Ausdehnung: {[round(x) for x in (m.bounds[1] - m.bounds[0])]}")
