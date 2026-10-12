import os
B = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ximaj_robosim")


def patch(fn, pairs):
    p = os.path.join(B, fn)
    m = open(p, encoding="utf8").read()
    for a, b in pairs:
        if a not in m:
            raise SystemExit(f"{fn}: NICHT GEFUNDEN:\n{a[:300]}")
        m = m.replace(a, b)
    open(p, "w", encoding="utf8").write(m)


patch("sim.py", [
    ('''    def tcp_in_base(self, q=None):
        return inv(self.base_mat()) @ self.tcp_world(q)''', '''    def base_world(self):
        """$BASE gilt relativ zum Roboterfuss (Roboter-Welt), wie bei realen Steuerungen."""
        return self.root @ self.base_mat()

    def tcp_in_base(self, q=None):
        return inv(self.base_world()) @ self.tcp_world(q)'''),
    ('''        T_base = pose_to_mat(*tgt[1])
        Tw = self.base_mat() @ T_base
        Tf = Tw @ inv(self.tool_mat())
        return inv(self.root) @ Tf''', '''        T_base = pose_to_mat(*tgt[1])
        return self.base_mat() @ T_base @ inv(self.tool_mat())'''),
])
patch("viewer.py", [("self._draw_axes(self.sim.base_mat(), 150, 0.4)", "self._draw_axes(self.sim.base_world(), 150, 0.4)")])
patch("main.py", [
    ("Tw[:3, 3] += self.sim.base_mat()[:3, :3] @ d", "Tw[:3, 3] += self.sim.base_world()[:3, :3] @ d"),
    ("Rb = self.sim.base_mat()[:3, :3]", "Rb = self.sim.base_world()[:3, :3]"),
    ('''            T = self.sim.base_mat() @ pose_to_mat(*w["pos"])
            ok = self.sim.model.ik(inv(self.sim.root) @ T @ inv(self.sim.tool_mat()), HOME) is not None''',
     '''            T = self.sim.base_mat() @ pose_to_mat(*w["pos"])
            ok = self.sim.model.ik(T @ inv(self.sim.tool_mat()), HOME) is not None'''),
    ('''        self.base_s = [spin(-20000, 20000, 0, 1, 10, cb=lambda _: self.apply_base()) for _ in range(6)]
        f.addRow("BASE X Y Z", row(*self.base_s[:3]))''', '''        self.base_s = [spin(-20000, 20000, 0, 1, 10, cb=lambda _: self.apply_base()) for _ in range(6)]
        f.addRow(QLabel("BASE bezieht sich auf den Roboterfuß"))
        f.addRow("BASE X Y Z", row(*self.base_s[:3]))'''),
])
# Singularitaets-Rueckfall fuer LIN
patch("sim.py", [
    ('''                try:
                    self.motion = self.plan_ptp(ev[1], ev[2]) if k == "ptp" else self.plan_lin(ev[1], ev[2])
                except PlanError as e:
                    self.state = "error"
                    self.say(f"Zeile {self.cur_line}: {e}")
                    return
                return''', '''                try:
                    self.motion = self.plan_ptp(ev[1], ev[2]) if k == "ptp" else self.plan_lin(ev[1], ev[2])
                except PlanError as e:
                    if k == "lin" and "Singular" in str(e):
                        try:
                            self.motion = self.plan_ptp(ev[1], ev[2])
                            self.say(f"Zeile {self.cur_line}: LIN durch Handgelenk-Singularität – als Achsbewegung ausgeführt")
                            return
                        except PlanError:
                            pass
                    self.state = "error"
                    self.say(f"Zeile {self.cur_line}: {e}")
                    return
                return'''),
])
print("ok")
