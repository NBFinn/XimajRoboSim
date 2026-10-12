import os
P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ximaj_robosim", "xrl.py")
m = open(P, encoding="utf8").read()


def rep(a, b):
    global m
    if a not in m:
        raise SystemExit("NICHT GEFUNDEN:\n" + a[:300])
    m = m.replace(a, b, 1)


rep('''    "DEFDAT", "ENDDAT", "DEFFCT", "ENDFCT",
}''', '''    "DEFDAT", "ENDDAT", "DEFFCT", "ENDFCT",
    "SPTP", "SLIN", "SCIRC", "SPTP_REL", "SLIN_REL", "SCIRC_REL", "CIRC_REL", "EXT", "EXTFCT", "INTERRUPT", "WITH",
}''')
rep('''            if v in ("PTP", "LIN", "PTP_REL", "LIN_REL"):
                self.nxt()
                tgt = self.expr()
                self.opt_approx()
                self.eol()
                return ("move", ln, v, tgt)
            if v == "CIRC":
                self.nxt()''', '''            if v == "GLOBAL":
                self.nxt()
                return self.stmt()
            if v in ("EXT", "EXTFCT", "INTERRUPT"):
                self.skipline()            # Deklarationen/Interrupts: in der Simulation ohne Wirkung
                return None
            if v in ("PTP", "LIN", "PTP_REL", "LIN_REL", "SPTP", "SLIN", "SPTP_REL", "SLIN_REL"):
                self.nxt()
                tgt = self.expr()
                self.rest_of_motion()
                kind = v[1:] if v.startswith("S") else v
                return ("move", ln, kind, tgt)
            if v in ("CIRC", "SCIRC", "CIRC_REL", "SCIRC_REL"):
                self.nxt()
                aux = self.expr()
                self.expect(",")
                tgt = self.expr()
                self.rest_of_motion()
                return ("circ", ln, aux, tgt)
            if v == "CIRC__ALT":
                self.nxt()''')
rep('''    def opt_approx(self):''', '''    def rest_of_motion(self):
        """Ueberschleifen (C_PTP/C_DIS/C_SPL), WITH-Zusaetze, CA ... bis Zeilenende ueberspringen"""
        while self.peek().k not in ("nl", "eof"):
            self.nxt()
        self.skipnl()

    def opt_approx(self):''')
rep('''                key = self.nxt().v
                items[key] = self.expr()
                self.accept(",")''', '''                key = self.nxt().v
                if self.is_("["):
                    while not self.is_("]") and self.peek().k not in ("nl", "eof"):
                        self.nxt()
                    self.accept("]")
                items[key] = self.expr()
                self.accept(",")''')
open(P, "w", encoding="utf8").write(m)
print("ok")
