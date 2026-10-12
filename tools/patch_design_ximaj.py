"""Design an ximaj.com anpassen: Kopfleiste, Logo, Startbild, Editorfarben, Roboter-Zierfarbe."""
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
    ('''        tb = QToolBar("Steuerung")
        tb.setMovable(False)
        self.addToolBar(tb)
        brand = QLabel(f"  ◆ {B['product']}   ")
        brand.setObjectName("brand")
        tb.addWidget(brand)''', '''        tb = QToolBar("Steuerung")
        tb.setObjectName("mainbar")
        tb.setMovable(False)
        self.addToolBar(tb)
        logo = QLabel()
        pm = QPixmap(theme.LOGO)
        if not pm.isNull():
            logo.setPixmap(pm.scaledToHeight(34, Qt.TransformationMode.SmoothTransformation))
        tb.addWidget(logo)
        brand = QLabel(f" {B['product'].upper()}   ")
        brand.setObjectName("brand")
        tb.addWidget(brand)'''),
    # Editor-Farben fuer hellen Hintergrund
    ('''                           fmt("#c084fc")))''', '''                           fmt("#7c3aed")))'''),
    ('''        self.rules.append((QRegularExpression(r"\\$[A-Za-z_][A-Za-z_0-9]*"), fmt("#60a5fa")))
        self.rules.append((QRegularExpression(r"\\b\\d+(\\.\\d+)?\\b"), fmt("#f5b83d")))
        self.rules.append((QRegularExpression(r"[;&].*$"), fmt("#6b7c99")))''', '''        self.rules.append((QRegularExpression(r"\\$[A-Za-z_][A-Za-z_0-9]*"), fmt("#0f766e")))
        self.rules.append((QRegularExpression(r"\\b\\d+(\\.\\d+)?\\b"), fmt("#b45309")))
        self.rules.append((QRegularExpression(r"[;&].*$"), fmt("#8a94a3")))'''),
    ('''            e.format.setBackground(QColor(B["accent_dark"]))''', '''            e.format.setBackground(QColor(B["accent_soft"]))'''),
    # Info-Dialog mit Logo
    ('''        QMessageBox.about(self, "Über", f"<h3>{B['product']} {VERSION}</h3><p>{B['tagline']}</p>"
                          f"<p>Eigenentwicklung der <b>{B['company']}</b>.</p>"
                          "<p>Eigenständige Software, nicht mit Dritt-Herstellern verbunden.</p>")''', '''        box = QMessageBox(self)
        box.setWindowTitle("Über")
        pm = QPixmap(theme.LOGO)
        if not pm.isNull():
            box.setIconPixmap(pm.scaledToHeight(96, Qt.TransformationMode.SmoothTransformation))
        box.setText(f"<h3 style='font-family:Saira,Bahnschrift'>{B['product']} {VERSION}</h3><p>{B['tagline']}</p>"
                    f"<p>Eigenentwicklung der <b>{B['company']}</b><br>"
                    "<a href='https://ximaj.com'>ximaj.com</a></p>"
                    "<p style='color:#5d6670'>Eigenständige Software, nicht mit Dritt-Herstellern verbunden.</p>")
        box.exec()'''),
    # Startbild wie Website-Hero
    ('''    ico = os.path.join(HERE, "assets", "ximaj_robosim.png")
    if os.path.exists(ico):
        app.setWindowIcon(QIcon(ico))
    w = MainWindow()
    w.show()''', '''    ico = os.path.join(HERE, "assets", "ximaj_robosim.png")
    if os.path.exists(ico):
        app.setWindowIcon(QIcon(ico))
    splash = make_splash()
    splash.show()
    app.processEvents()
    w = MainWindow()
    w.show()
    splash.finish(w)'''),
    ('''def main():''', '''def make_splash():
    """Startbild im Stil der Website: Navy-Verlauf, Schild-Logo, Schriftzug."""
    from PyQt6.QtWidgets import QSplashScreen
    from PyQt6.QtGui import QLinearGradient, QFont as _F
    W, H = 640, 360
    pm = QPixmap(W, H)
    p = QPainter(pm)
    g = QLinearGradient(0, 0, W, H * 0.47)
    g.setColorAt(0.0, QColor(B["navy"]))
    g.setColorAt(0.4, QColor(B["navy"]))
    g.setColorAt(1.0, QColor(B["navy_end"]))
    p.fillRect(0, 0, W, H, g)
    logo = QPixmap(theme.LOGO)
    if not logo.isNull():
        lg = logo.scaledToHeight(150, Qt.TransformationMode.SmoothTransformation)
        p.drawPixmap(60, (H - lg.height()) // 2 - 10, lg)
    p.setPen(QColor("white"))
    f = _F("Saira")
    if f.family() != "Saira":
        f = _F("Bahnschrift")
    f.setPointSize(26)
    f.setWeight(_F.Weight.Medium)
    p.setFont(f)
    p.drawText(240, 160, "XIMAJ ROBOSIM")
    f.setPointSize(11)
    f.setWeight(_F.Weight.Normal)
    p.setFont(f)
    p.setPen(QColor(255, 255, 255, 190))
    p.drawText(242, 192, B["tagline"])
    p.drawText(242, 300, f"Version {VERSION}  ·  {B['company']}")
    p.fillRect(242, 210, 56, 3, QColor(B["accent"]))
    p.end()
    s = QSplashScreen(pm)
    s.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    return s


def main():'''),
])

patch("viewer.py", [
    ('''        accent = hexrgb(theme.BRAND["accent"])''', '''        accent = hexrgb(theme.BRAND.get("robot_trim", theme.BRAND["accent"]))'''),
])
print("ok")
