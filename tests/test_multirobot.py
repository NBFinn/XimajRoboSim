"""Zwei Roboter + Linearachse + Senke: gleichzeitiger Lauf, Handshake ueber E/A, Durchsatz."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'ximaj_robosim'))
from sim import Simulation, SceneObj

s = Simulation()
r1 = s.active
r1.name = "Lader"
r1.tool.grip_out = 1
r2 = s.add_robot("XR-9 (0.9 m, 6 kg)", (0, 1300, 0, 0, 0, 0), name="Entlader")
r2.tool.grip_out = 2
r2.set_track(e_min=0, e_max=3000, vmax=1200)
s.scene = [SceneObj("Tisch", "box", (500, 1000, 0), (0, 0, 0), (400, 2400, 20), "#64748b", True, False),
           SceneObj("Teil", "workpiece", (450, 250, 20), (0, 0, 0), (60, 40, 40), "#f5b83d", False, True),
           SceneObj("Senke", "sink", (2900, 1600, 0), (0, 0, 0), (300, 300, 300), "#16a34a", False, False)]
# Roboter 1 legt Teil in die Mitte und meldet ueber $OUT[10]
r1.src = """DEF lader()
  PTP {X 450, Y 250, Z 300, A 0, B 0, C 180}
  LIN {X 450, Y 250, Z 45, A 0, B 0, C 180}
  $OUT[1] = TRUE
  WAIT SEC 0.3
  LIN {X 450, Y 250, Z 300, A 0, B 0, C 180}
  PTP {X 450, Y 750, Z 300, A 0, B 0, C 180}
  LIN {X 450, Y 750, Z 45, A 0, B 0, C 180}
  $OUT[1] = FALSE
  WAIT SEC 0.3
  PTP {X 300, Y 0, Z 600, A 0, B 0, C 180}
  $OUT[10] = TRUE
END
"""
# Roboter 2 wartet, holt das Teil, faehrt auf der Linearachse und wirft es in die Senke
r2.src = """DEF entlader()
  WAIT FOR $OUT[10]
  PTP {X 450, Y -550, Z 300, A 0, B 0, C 180, E1 0}
  LIN {X 450, Y -550, Z 45, A 0, B 0, C 180}
  $OUT[2] = TRUE
  WAIT SEC 0.3
  LIN {X 450, Y -550, Z 400, A 0, B 0, C 180}
  PTP {X 2900, Y 300, Z 500, A 0, B 0, C 180, E1 2500}
  $OUT[2] = FALSE
  WAIT SEC 1.0
END
"""
s.stop_on_collision = False
s.start_all()
for i in range(60 * 90):
    s.tick(1 / 60)
    if not s.any_busy():
        break
for r in s.robots:
    print(f"{r.name:9s} {r.state:7s} E1={r.e1:7.1f}  Kollision={r.collision}")
print("Durchsatz:", {k: round(v, 1) if isinstance(v, float) else v for k, v in s.throughput().items()})
print("\n".join(s.log[-8:]))
