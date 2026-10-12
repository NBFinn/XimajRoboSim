"""Statement-Programm (Bausteine) erzeugen, pruefen und ausfuehren."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'ximaj_robosim'))
import statements as stm
from sim import Simulation, SceneObj

s = Simulation()
s.scene = [SceneObj("Teil", "workpiece", (450, 250, 20), (0, 0, 0), (60, 40, 40), "#f5b83d", False, True),
           SceneObj("Tisch", "box", (500, 0, 0), (0, 0, 0), (600, 1000, 20), "#64748b", True, False)]
P = lambda x, y, z: [x, y, z, 0, 0, 180]
prog = [
    stm.new("COMMENT", text="Pick & Place aus Bausteinen"),
    stm.new("VEL", cp=1.0, ptp=80),
    stm.new("PTP", pos=P(450, 0, 600)),
    stm.new("LOOP", count=2),
    stm.new("PTP", pos=P(450, 250, 300)),
    stm.new("LIN", pos=P(450, 250, 45)),
    stm.new("GRIP", nr=1),
    stm.new("LIN", pos=P(450, 250, 300)),
    stm.new("IF", kind="OUT", nr=1, value=True),
    stm.new("PTP", pos=P(450, -250, 300)),
    stm.new("LIN", pos=P(450, -250, 45)),
    stm.new("ELSE"),
    stm.new("MSG", text="nichts gegriffen"),
    stm.new("IF_END"),
    stm.new("RELEASE", nr=1),
    stm.new("LIN", pos=P(450, -250, 300)),
    stm.new("LOOP_END"),
    stm.new("PULSE", nr=5, sec=0.5),
    stm.new("PTP", pos=P(450, 0, 600)),
]
print("Pruefung:", stm.validate(prog) or "OK")
src, lm = stm.generate(prog, "bausteine")
print(src)
r = s.active
r.statements, r.mode = prog, "statements"
r.load_program(src)
r.stmt_linemap = lm
s.start_all()
visited = set()
for i in range(60 * 60):
    s.tick(1 / 60)
    if r.cur_line in lm:
        visited.add(lm[r.cur_line])
    if not s.any_busy():
        break
print("Zustand:", r.state, "| Teil:", [round(v) for v in s.scene[0].pos], "| besuchte Bausteine:", sorted(visited))
print("Fehlerhafter Aufbau ->", stm.validate([stm.new("LOOP"), stm.new("IF_END")]))
