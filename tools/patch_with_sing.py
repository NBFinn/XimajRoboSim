import os
B = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ximaj_robosim")


def patch(fn, pairs):
    p = os.path.join(B, fn)
    m = open(p, encoding="utf8").read()
    for a, b in pairs:
        if a not in m:
            raise SystemExit(f"{fn}: NICHT GEFUNDEN:\n{a[:300]}")
        m = m.replace(a, b, 1)
    open(p, "w", encoding="utf8").write(m)


# ---------------- Kinematik: stabile Handgelenk-Singularitaet
patch("kinematics.py", [
    ('''                for q4, q5, q6 in cands:
                    sols.append([q1 * R2D, q2 * R2D, q3 * R2D,
                                 None if q4 is None else q4 * R2D, q5 * R2D, q6 * R2D])''',
     '''                for q4, q5, q6 in cands:
                    sols.append([q1 * R2D, q2 * R2D, q3 * R2D,
                                 None if q4 is None else q4 * R2D, q5 * R2D, q6 * R2D, r36])'''),
    ('''        for s in self.ik_all(T):
            q = []''', '''        sols = self.ik_all(T)
        # nahe der Handgelenk-Singularitaet: Loesung mit unveraendertem A4 ergaenzen (kein A4/A6-Sprung)
        extra = []
        for s in sols:
            r36 = s[6]
            if math.hypot(r36[0, 2], r36[1, 2]) < 0.08:
                c4 = q_ref[3] * D2R
                Rp = rz(-c4)[:3, :3] @ r36
                if abs(Rp[1, 2]) < 2e-3:
                    extra.append([s[0], s[1], s[2], q_ref[3], math.atan2(Rp[0, 2], Rp[2, 2]) * R2D,
                                  math.atan2(Rp[1, 0], Rp[1, 1]) * R2D, r36])
        for s in sols + extra:
            q = []'''),
])

# ---------------- XRL: WITH-Zusaetze auswerten
patch("xrl.py", [
    ('''            if v in ("PTP", "LIN", "PTP_REL", "LIN_REL", "SPTP", "SLIN", "SPTP_REL", "SLIN_REL"):
                self.nxt()
                tgt = self.expr()
                self.rest_of_motion()
                kind = v[1:] if v.startswith("S") else v
                return ("move", ln, kind, tgt)''', '''            if v in ("PTP", "LIN", "PTP_REL", "LIN_REL", "SPTP", "SLIN", "SPTP_REL", "SLIN_REL"):
                self.nxt()
                tgt = self.expr()
                withs = self.with_clause()
                self.rest_of_motion()
                kind = v[1:] if v.startswith("S") else v
                return ("move", ln, kind, tgt, withs)'''),
    ('''                tgt = self.expr()
                self.rest_of_motion()
                return ("circ", ln, aux, tgt)''', '''                tgt = self.expr()
                withs = self.with_clause()
                self.rest_of_motion()
                return ("circ", ln, aux, tgt, withs)'''),
    ('''    def rest_of_motion(self):''', '''    def with_clause(self):
        """WITH $TOOL = STOOL2(F), $VEL_AXIS[1] = SVEL_JOINT(100) ... -> [(ziel, ausdruck)]"""
        out = []
        if not self.accept("WITH"):
            return out
        try:
            while True:
                t = self.expr()
                self.expect("=")
                v = self.expr()
                out.append((t, v))
                if not self.accept(","):
                    break
        except XrlError:
            pass
        return out

    def rest_of_motion(self):'''),
    ('''        if k == "move":
            tgt = self.target(self.ev(s[3], env), env, rel=s[2].endswith("_REL"))''', '''        if k in ("move", "circ") and len(s) > 4 and s[-1]:
            self.apply_with(s[-1], env)
        if k == "move":
            tgt = self.target(self.ev(s[3], env), env, rel=s[2].endswith("_REL"))'''),
    ('''    def bas(self, args):''', '''    def apply_with(self, withs, env):
        """Nur die fuer die Simulation relevanten Zusaetze: Werkzeug, Basis, Geschwindigkeit."""
        for t, v in withs:
            name = t[1] if t[0] == "var" else (t[1][1] if t[0] == "idx" and t[1][0] == "var" else "")
            if name not in ("$TOOL", "$BASE", "$VEL_AXIS", "$VEL", "$VEL.CP"):
                continue
            try:
                val = self.ev(v, env)
            except XrlError:
                continue
            if name == "$TOOL" and isinstance(val, dict):
                self.sv["TOOL"] = dict(val)
            elif name == "$BASE" and isinstance(val, dict):
                self.sv["BASE"] = dict(val)
            elif name == "$VEL_AXIS" and isinstance(val, (int, float)) and val > 0:
                self.sv["VEL_AXIS_PCT"] = max(0.01, min(1.0, float(val) / 100.0))
            elif name in ("$VEL", "$VEL.CP") and isinstance(val, (int, float)) and val > 0:
                self.sv["VEL_CP"] = float(val)

    def builtin(self, n, args):
        """Kompatible Hilfsfunktionen fuer Bewegungszusaetze. -> (gefunden, wert)"""
        td, bd = self.glob.get("TOOL_DATA"), self.glob.get("BASE_DATA")
        if n == "STOOL2" and args and isinstance(args[0], dict):
            i = int(args[0].get("TOOL_NO", 0))
            return True, (td[i] if isinstance(td, list) and 0 <= i < len(td) else {})
        if n == "SBASE" and args:
            i = int(args[0]) if not isinstance(args[0], dict) else int(args[0].get("BASE_NO", 0))
            return True, (bd[i] if isinstance(bd, list) and 0 <= i < len(bd) else {})
        if n in ("SVEL_JOINT", "SVEL_CP", "SACC_JOINT", "SACC_CP") and args:
            return True, args[0] if isinstance(args[0], (int, float)) else 0
        return False, None

    def bas(self, args):'''),
    ('''            if n in FUNCS:
                return FUNCS[n](*args)
            if n in self.defs:''', '''            if n in FUNCS:
                return FUNCS[n](*args)
            ok, val = self.builtin(n, args)
            if ok:
                return val
            if n in self.defs:'''),
])
print("ok")
