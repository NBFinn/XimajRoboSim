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
    ('''        self.track = None                          # {"length": mm, "vmax": mm/s, "name": str}''',
     '''        self.track = None                          # {"min": mm, "max": mm, "vmax": mm/s, "name": str}'''),
    ('''    def set_track(self, length=None, vmax=1500.0, name="Linearachse"):
        """Linearachse E1 entlang der X-Achse des Roboterfusses. length=None -> keine Achse"""
        if not length:
            self.track, self.e1 = None, 0.0
        else:
            self.track = {"length": float(length), "vmax": float(vmax), "name": name}
            self.e1 = float(np.clip(self.e1, 0, length))
        self.update_sv()''', '''    def set_track(self, length=None, vmax=1500.0, name="Linearachse", e_min=None, e_max=None):
        """Linearachse E1 entlang der X-Achse des Roboterfusses. length=None und keine Grenzen -> keine Achse"""
        if not length and e_min is None and e_max is None:
            self.track, self.e1 = None, 0.0
        else:
            lo = float(e_min if e_min is not None else 0.0)
            hi = float(e_max if e_max is not None else lo + float(length))
            self.track = {"min": lo, "max": hi, "vmax": float(vmax), "name": name}
            self.e1 = float(np.clip(self.e1, lo, hi))
        self.update_sv()

    def e_limits(self):
        if self.track is None:
            return 0.0, 0.0
        if "min" not in self.track:          # aelteres Format
            self.track = {"min": 0.0, "max": self.track.get("length", 0.0), "vmax": self.track.get("vmax", 1500.0),
                          "name": self.track.get("name", "Linearachse")}
        return self.track["min"], self.track["max"]'''),
    ('''        return float(np.clip(float(e), 0, self.track["length"]))''', '''        return float(np.clip(float(e), *self.e_limits()))'''),
    ('''                    e1 = float(np.clip(e0 + float(tgt[2]), 0, self.track["length"]))''',
     '''                    e1 = float(np.clip(e0 + float(tgt[2]), *self.e_limits()))'''),
    ('''        es = [self.e1] if self.track is None else list(np.linspace(0, self.track["length"], 11))''',
     '''        es = [self.e1] if self.track is None else list(np.linspace(*self.e_limits(), 11))'''),
    ('''        self.track = d.get("track")
        self.e1 = float(d.get("e1", 0.0))''', '''        self.track = d.get("track")
        self.e_limits()
        self.e1 = float(d.get("e1", 0.0))'''),
])
patch("viewer.py", [
    ('''        L = r.track["length"]
        s = r.model.reach / 1000.0''', '''        lo, hi = r.e_limits()
        L = hi - lo
        s = r.model.reach / 1000.0'''),
    ('''        M = r.root
        self._lbox(M, (L / 2, 0, 60), (L + w, w, 120), frame)''', '''        M = r.root @ pose_to_mat(lo, 0, -150, 0, 0, 0)
        self._lbox(M, (L / 2, 0, 60), (L + w, w, 120), frame)'''),
])
patch("vcmx_import.py", [
    ('''        if rb and rnode is not comp:
            sub = location(rnode)
            if sub:
                M = M @ _mat(sub)
            log.append(f"'{rnode.name()}' ist auf '{name}' montiert (Zusatzachse nicht simuliert)")
            name = rnode.name() or name''', '''        track = None
        if rb and rnode is not comp:
            sub = location(rnode)
            if sub:
                M = M @ _mat(sub)
            cv = _vars(comp)
            travel = _num(cv.get("Rated_travel")) or _num(cv.get("TravelLength")) or _num(cv.get("Length"))
            if travel:
                # Software-Endschalter wie in der Achse hinterlegt (typisch: -Verfahrweg+200 ... +150)
                lo = -(travel - 200.0) if "Softn_end" in cv else 0.0
                hi = 150.0 if "Softp_end" in cv else travel
                track = (lo, hi)
                log.append(f"'{rnode.name()}' auf Linearachse '{name}': E1 {lo:.0f} … {hi:.0f} mm")
            else:
                log.append(f"'{rnode.name()}' ist auf '{name}' montiert (Zusatzachse ohne Verfahrweg)")
            name = rnode.name() or name'''),
    ('''            p = mat_to_pose(M)
            sim.set_root([float(x) for x in p])
            robot_done = True''', '''            p = mat_to_pose(M)
            sim.set_root([float(x) for x in p])
            if track and hasattr(sim, "set_track"):
                sim.set_track(e_min=track[0], e_max=track[1], vmax=1500.0, name="Linearachse")
            robot_done = True'''),
])
print("ok")
