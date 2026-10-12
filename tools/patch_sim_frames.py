import os
P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ximaj_robosim", "sim.py")
m = open(P, encoding="utf8").read()


def rep(a, b):
    global m
    if a not in m:
        raise SystemExit("NICHT GEFUNDEN:\n" + a[:300])
    m = m.replace(a, b, 1)


rep('''        self.waypoints = []                        # eingelernte Punkte''', '''        self.waypoints = []                        # eingelernte Punkte
        self.tool_table = {}                       # Nr -> {"name", "frame":[x,y,z,a,b,c]}  (TOOL_DATA)
        self.base_table = {}                       # Nr -> {"name", "frame":[...]}         (BASE_DATA)
        self.imported_models = {}                  # aus alten Projekten erzeugte Robotermodelle''')
rep('''    def tool_mat(self):
        return self.tool.matrix()

    def base_mat(self):
        return pose_to_mat(*self.base)''', '''    @staticmethod
    def _frame_from_sv(v):
        if isinstance(v, dict) and any(k in v for k in ("X", "Y", "Z", "A", "B", "C")):
            return pose_to_mat(*[float(v.get(k, 0)) for k in ("X", "Y", "Z", "A", "B", "C")])
        return None

    def tool_mat(self):
        m = self._frame_from_sv(self.sv.get("TOOL")) if self.state != "idle" else None
        return m if m is not None else self.tool.matrix()

    def base_mat(self):
        m = self._frame_from_sv(self.sv.get("BASE")) if self.state != "idle" else None
        return m if m is not None else pose_to_mat(*self.base)

    def frame_tables(self):
        """TOOL_DATA[0..16] / BASE_DATA[0..32] als Listen fuer den Interpreter"""
        keys = ("X", "Y", "Z", "A", "B", "C")
        td = [dict(zip(keys, [0.0] * 6)) for _ in range(17)]
        bd = [dict(zip(keys, [0.0] * 6)) for _ in range(33)]
        for n, t in self.tool_table.items():
            if 0 <= int(n) < 17:
                td[int(n)] = dict(zip(keys, map(float, t["frame"])))
        for n, t in self.base_table.items():
            if 0 <= int(n) < 33:
                bd[int(n)] = dict(zip(keys, map(float, t["frame"])))
        return {"TOOL_DATA": td, "BASE_DATA": bd}''')
rep('''            self.interp = Interp(self.src, self.io, self.sv)
            self.sv["TOOL"], self.sv["BASE"] = {}, {}''', '''            self.sv["TOOL"], self.sv["BASE"] = {}, {}
            self.sv["VEL_AXIS_PCT"] = 1.0
            self.interp = Interp(self.src, self.io, self.sv, self.frame_tables())
            for w in self.interp.warnings[:30]:
                self.say(f"Hinweis: {w}")''')
rep('''        self.reset_program()
        self.state = "stopped"
        self.say("Programm gestoppt")''', '''        self.reset_program()
        self.state = "stopped"
        self.say("Programm gestoppt")

    def flush_warnings(self):
        if self.interp is not None:
            new = self.interp.warnings[getattr(self, "_wn", 0):]
            for w in new[:20]:
                self.say(f"Hinweis: {w}")
            self._wn = len(self.interp.warnings)''')
rep('''            "program": self.src, "safety": self.safety, "waypoints": self.waypoints,''', '''            "program": self.src, "safety": self.safety, "waypoints": self.waypoints,
            "tool_table": self.tool_table, "base_table": self.base_table,
            "imported_models": self.imported_models,''')
rep('''    def from_dict(self, d):
        self.set_model(d.get("model", self.model_key))''', '''    def from_dict(self, d):
        from kinematics import RobotModel
        self.imported_models = d.get("imported_models", {})
        for k, p in self.imported_models.items():
            MODELS[k] = RobotModel(k, *p["dims"], p["limits"], p["vmax"], p.get("payload", 0))
        self.tool_table = d.get("tool_table", {})
        self.base_table = d.get("base_table", {})
        self.set_model(d.get("model", self.model_key) if d.get("model") in MODELS else self.model_key)''')
open(P, "w", encoding="utf8").write(m)
print("ok")
