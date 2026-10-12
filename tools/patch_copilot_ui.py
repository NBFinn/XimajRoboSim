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


patch("main.py", [
    ("import cad\n", "import cad\nimport copilot\n"),
    # Copilot-Eingabe in der Kopfleiste
    ('''        self.state_l = QLabel("")
        tb.addSeparator()
        tb.addWidget(self.state_l)''', '''        self.state_l = QLabel("")
        tb.addSeparator()
        tb.addWidget(self.state_l)
        tb.addSeparator()
        self.cop_in = QLineEdit()
        self.cop_in.setPlaceholderText("✦ Copilot: z. B. „füge ein Förderband 3 m bei x 1500 y -800 hinzu“")
        self.cop_in.setMinimumWidth(380)
        self.cop_in.setStyleSheet("QLineEdit{background:rgba(255,255,255,0.12);color:white;border:1px solid "
                                  "rgba(255,255,255,0.3);border-radius:8px;padding:5px 10px}")
        self.cop_in.returnPressed.connect(self.copilot_run)
        tb.addWidget(self.cop_in)'''),
    ('''    # ----- Prozesse (Bahn / Punkt / Flaeche)''', '''    # ----- Copilot
    def copilot_run(self):
        txt = self.cop_in.text().strip()
        if not txt:
            return
        try:
            ans = copilot.execute(self, txt)
        except Exception as e:
            ans = f"Fehler: {e}"
        self.cop_in.clear()
        self.log_msg(f"Copilot ▸ {txt}")
        for line in ans.splitlines():
            self.log_msg(f"Copilot ◂ {line}")
        self.statusBar().showMessage(f"Copilot: {ans.splitlines()[0]}", 8000)
        self.viewer.update()

    # ----- Prozesse (Bahn / Punkt / Flaeche)'''),
])
print("ok")
