"""Menueband (Ribbon) im Ximaj-Design: Reiter mit Gruppen, grossen/kleinen Schaltflaechen und Optionen.

Aufbau:   rb = Ribbon(); p = rb.add_tab("START"); g = p.group("Zwischenablage")
          g.large("Verschieben", "move", fn, checkable=True); g.small("Kopieren", "copy", fn)
          g.check("Immer fangen", True, fn); g.radio("Zur Welt", "fix", False, fn); g.spin("Größe", 500, " mm", fn)
Die Datei-Schaltflaeche oeffnet die Backstage-Ansicht (Backstage-Klasse).
"""
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QEvent
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel, QToolButton, QCheckBox, QRadioButton,
                             QButtonGroup, QDoubleSpinBox, QStackedWidget, QFrame, QScrollArea, QMenu, QSizePolicy,
                             QPushButton, QListWidget, QListWidgetItem, QLineEdit, QComboBox)

import theme
from icons import icon

B = theme.BRAND


def stylesheet():
    grad = theme.navy_gradient()
    return f"""
    QWidget#ribbon {{ background: {B['panel']}; }}
    QWidget#ribbon_head {{ background: {grad}; }}
    QToolButton#rtab {{ background: transparent; color: rgba(255,255,255,0.72); border: none; border-radius: 0;
        padding: 8px 16px 7px 16px; font-family: {B['font_head']}; font-size: 10pt; font-weight: 500; letter-spacing: 0.8px; }}
    QToolButton#rtab:hover {{ color: white; background: rgba(255,255,255,0.08); }}
    QToolButton#rtab:checked {{ color: white; background: {B['panel']}; border-top-left-radius: 8px;
        border-top-right-radius: 8px; border-bottom: 2px solid {B['accent']}; }}
    QToolButton#rfile {{ background: {B['accent']}; color: white; border: none; border-radius: 0; padding: 8px 20px 7px 20px;
        font-family: {B['font_head']}; font-size: 10pt; font-weight: 500; letter-spacing: 0.8px; }}
    QToolButton#rfile:hover {{ background: {B['accent_hover']}; }}
    QToolButton#rhead {{ background: transparent; border: none; color: white; padding: 4px 8px; }}
    QToolButton#rhead:hover {{ background: rgba(255,255,255,0.12); }}
    QLabel#rbrand {{ color: white; font-family: {B['font_head']}; font-size: 11pt; font-weight: 500; letter-spacing: 1.5px;
        padding: 0 10px; background: transparent; }}
    QWidget#rpage {{ background: {B['panel']}; border-bottom: 1px solid {B['border']}; }}
    QScrollArea {{ background: {B['panel']}; border: none; }}
    QFrame#rgroup {{ background: transparent; border: none; border-right: 1px solid rgba(255,255,255,0.08); }}
    QLabel#rgtitle {{ color: {B['muted']}; font-size: 8.5pt; padding: 0 2px 2px 2px; background: transparent; }}
    QToolButton#rlarge {{ background: transparent; border: 1px solid transparent; border-radius: 8px; padding: 3px 4px;
        color: {B['text']}; font-size: 9pt; }}
    QToolButton#rlarge:hover {{ background: rgba(255,255,255,0.08); border-color: rgba(255,255,255,0.16); }}
    QToolButton#rlarge:checked {{ background: {B['accent_soft']}; border-color: {B['accent']}; color: white; }}
    QToolButton#rlarge:disabled {{ color: #5f7090; }}
    QToolButton#rsmall {{ background: transparent; border: 1px solid transparent; border-radius: 6px; padding: 1px 6px 1px 3px;
        color: {B['text']}; font-size: 9pt; text-align: left; }}
    QToolButton#rsmall:hover {{ background: rgba(255,255,255,0.08); border-color: rgba(255,255,255,0.16); }}
    QToolButton#rsmall:checked {{ background: {B['accent_soft']}; border-color: {B['accent']}; }}
    QToolButton#rsmall:disabled {{ color: #5f7090; }}
    QWidget#rpage QCheckBox, QWidget#rpage QRadioButton {{ font-size: 9pt; spacing: 6px; background: transparent; }}
    QWidget#rpage QDoubleSpinBox, QWidget#rpage QLineEdit {{ padding: 1px 4px; font-size: 9pt; }}
    QWidget#backstage {{ background: {B['panel']}; }}
    QWidget#bs_nav {{ background: {grad}; }}
    QPushButton#bs_item {{ background: transparent; color: rgba(255,255,255,0.86); border: none; border-radius: 0;
        text-align: left; padding: 11px 22px; font-family: {B['font_head']}; font-size: 11pt; }}
    QPushButton#bs_item:hover {{ background: rgba(255,255,255,0.10); color: white; }}
    QPushButton#bs_back {{ background: transparent; color: white; border: none; text-align: left; padding: 14px 18px;
        font-size: 16pt; }}
    QPushButton#bs_back:hover {{ background: rgba(255,255,255,0.10); }}
    QLabel#bs_title {{ font-family: {B['font_head']}; font-size: 22pt; font-weight: 500; color: white; }}
    """


class Group(QFrame):
    """Gruppe im Menueband: Inhalt oben, Titel unten; kleine Elemente stapeln sich zu je drei."""

    def __init__(self, title):
        super().__init__()
        self.setObjectName("rgroup")
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 4, 6, 0)
        v.setSpacing(0)
        self.row = QHBoxLayout()
        self.row.setSpacing(2)
        self.row.setContentsMargins(0, 0, 0, 0)
        v.addLayout(self.row, 1)
        t = QLabel(title)
        t.setObjectName("rgtitle")
        t.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        v.addWidget(t)
        self._col = None
        self._n = 0
        self.items = {}

    def _stack(self, w):
        if self._col is None or self._n >= 3:
            box = QWidget()
            self._col = QVBoxLayout(box)
            self._col.setContentsMargins(0, 0, 0, 0)
            self._col.setSpacing(1)
            self._col.setAlignment(Qt.AlignmentFlag.AlignTop)
            self.row.addWidget(box)
            self._n = 0
        self._col.addWidget(w)
        self._n += 1
        return w

    def column(self):
        """naechste kleine Elemente in einer neuen Spalte beginnen"""
        self._col = None

    def _wire(self, b, fn, checkable, tip, enabled):
        b.setCheckable(checkable)
        b.setEnabled(enabled)
        if tip:
            b.setToolTip(tip)
        if fn:
            if checkable:
                b.toggled.connect(lambda c: fn(c))
            else:
                b.clicked.connect(lambda: fn())

    def large(self, text, icon_name, fn=None, checkable=False, tip=None, menu=None, enabled=True, checked=False):
        b = QToolButton()
        b.setObjectName("rlarge")
        b.setText(text)
        b.setIcon(icon(icon_name, 32))
        b.setIconSize(QSize(32, 32))
        b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        fm = b.fontMetrics()
        b.setMinimumWidth(max(56, max(fm.horizontalAdvance(t) for t in text.splitlines()) + 22))
        b.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        b.setCheckable(checkable)
        if checked:
            b.setChecked(True)            # vor dem Verbinden, damit kein Signal beim Aufbau feuert
        self._wire(b, fn, checkable, tip, enabled)
        if menu:
            m = QMenu(b)
            for entry in menu:
                if entry is None:
                    m.addSeparator()
                    continue
                label, f = entry
                a = m.addAction(label)
                a.triggered.connect(lambda _=False, f=f: f())
            b.setMenu(m)
            b.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup if fn else
                           QToolButton.ToolButtonPopupMode.InstantPopup)
        self._col = None
        self.row.addWidget(b)
        self.items[text] = b
        return b

    def small(self, text, icon_name, fn=None, checkable=False, tip=None, enabled=True, checked=False):
        b = QToolButton()
        b.setObjectName("rsmall")
        b.setText(text)
        b.setIcon(icon(icon_name, 16))
        b.setIconSize(QSize(16, 16))
        b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        b.setCheckable(checkable)
        if checked:
            b.setChecked(True)
        self._wire(b, fn, checkable, tip, enabled)
        self.items[text] = b
        return self._stack(b)

    def check(self, text, checked=False, fn=None, tip=None):
        c = QCheckBox(text)
        c.setChecked(checked)
        if tip:
            c.setToolTip(tip)
        if fn:
            c.toggled.connect(lambda v: fn(v))
        self.items[text] = c
        return self._stack(c)

    def radio(self, text, group, checked=False, fn=None, tip=None):
        r = QRadioButton(text)
        r.setChecked(checked)
        if tip:
            r.setToolTip(tip)
        if not hasattr(self, '_radio_groups'):
            self._radio_groups = {}
        bg = self._radio_groups.get(group)
        if bg is None:
            bg = self._radio_groups[group] = QButtonGroup(self)
        bg.addButton(r)
        if fn:
            r.toggled.connect(lambda v: v and fn())
        self.items[text] = r
        return self._stack(r)

    def spin(self, label, value, suffix="", fn=None, lo=0.0, hi=100000.0, step=10.0, tip=None):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)
        h.addWidget(QLabel(label))
        s = QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setDecimals(0)
        s.setSingleStep(step)
        s.setSuffix(suffix)
        s.setValue(value)
        s.setFixedWidth(96)
        if tip:
            s.setToolTip(tip)
        if fn:
            s.valueChanged.connect(lambda v: fn(v))
        h.addWidget(s)
        self.items[label] = s
        self._stack(w)
        return s

    def widget(self, w):
        self._col = None
        self.row.addWidget(w)
        return w


class Page(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("rpage")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.h = QHBoxLayout(self)
        self.h.setContentsMargins(4, 3, 4, 2)
        self.h.setSpacing(0)
        self.h.addStretch(1)
        self.groups = {}

    def group(self, title):
        g = Group(title)
        self.h.insertWidget(self.h.count() - 1, g)
        self.groups[title] = g
        return g


class Ribbon(QWidget):
    file_clicked = pyqtSignal()
    tab_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ribbon")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(stylesheet())
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        head = QWidget()
        head.setObjectName("ribbon_head")
        head.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.hl = QHBoxLayout(head)
        self.hl.setContentsMargins(0, 0, 6, 0)
        self.hl.setSpacing(0)
        f = QToolButton()
        f.setObjectName("rfile")
        f.setText("DATEI")
        f.clicked.connect(self.file_clicked.emit)
        self.hl.addWidget(f)
        self.tabs_box = QHBoxLayout()
        self.tabs_box.setSpacing(2)
        self.tabs_box.setContentsMargins(6, 4, 0, 0)
        self.hl.addLayout(self.tabs_box)
        self.compact_tabs = QComboBox()
        self.compact_tabs.setAccessibleName('Menübandbereich auswählen')
        self.compact_tabs.setMinimumWidth(170)
        self.compact_tabs.currentTextChanged.connect(lambda title: title and self.select(title))
        self.hl.addWidget(self.compact_tabs)
        self.compact_tabs.hide()
        self.hl.addStretch(1)
        self.right = QHBoxLayout()
        self.right.setSpacing(4)
        self.hl.addLayout(self.right)
        self.btn_collapse = QToolButton()
        self.btn_collapse.setObjectName("rhead")
        self.btn_collapse.setText("︿")
        self.btn_collapse.setToolTip("Menüband ein-/ausklappen (Strg+F1)")
        self.btn_collapse.clicked.connect(self.toggle_collapsed)
        self.hl.addWidget(self.btn_collapse)
        v.addWidget(head)
        self.stack = QStackedWidget()
        self.stack.setFixedHeight(104)
        v.addWidget(self.stack)
        self.tabs = []
        self.pages = {}
        self.collapsed = False

    def add_head_widget(self, w):
        self.right.addWidget(w)
        return w

    def add_tab(self, title):
        b = QToolButton()
        b.setObjectName("rtab")
        b.setText(title)
        b.setCheckable(True)
        b.clicked.connect(lambda _=False, t=title: self.select(t))
        self.tabs_box.addWidget(b)
        p = Page()
        sa = QScrollArea()
        sa.setWidget(p)
        sa.setWidgetResizable(True)
        sa.setFrameShape(QScrollArea.Shape.NoFrame)
        sa.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.stack.addWidget(sa)
        self.tabs.append((title, b, sa))
        self.pages[title] = p
        self.compact_tabs.blockSignals(True)
        self.compact_tabs.addItem(title)
        self.compact_tabs.blockSignals(False)
        if len(self.tabs) == 1:
            self.select(title)
        return p

    def select(self, title):
        self.compact_tabs.blockSignals(True)
        self.compact_tabs.setCurrentText(title)
        self.compact_tabs.blockSignals(False)
        for t, b, sa in self.tabs:
            b.setChecked(t == title)
            if t == title:
                self.stack.setCurrentWidget(sa)
        if self.collapsed:
            self.toggle_collapsed()
        self.tab_changed.emit(title)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        compact = self.width() < 1100
        self.compact_tabs.setVisible(compact)
        for title, button, _ in self.tabs:
            button.setVisible(not compact)
        for i in range(self.right.count()):
            widget = self.right.itemAt(i).widget()
            if widget:
                widget.setVisible(not compact)

    def current(self):
        return next((t for t, b, _ in self.tabs if b.isChecked()), None)

    def toggle_collapsed(self):
        self.collapsed = not self.collapsed
        self.stack.setVisible(not self.collapsed)
        self.btn_collapse.setText("﹀" if self.collapsed else "︿")


class Backstage(QWidget):
    """Datei-Ansicht: linke Navigationsleiste, rechts Inhalte (Zuletzt verwendet, Info)."""
    closed = pyqtSignal()

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("backstage")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(stylesheet())
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        nav = QWidget()
        nav.setObjectName("bs_nav")
        nav.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        nav.setFixedWidth(250)
        self.nv = QVBoxLayout(nav)
        self.nv.setContentsMargins(0, 0, 0, 12)
        self.nv.setSpacing(0)
        back = QPushButton("←")
        back.setObjectName("bs_back")
        back.clicked.connect(self.hide_stage)
        self.nv.addWidget(back)
        h.addWidget(nav)
        self.body = QWidget()
        self.bl = QVBoxLayout(self.body)
        self.bl.setContentsMargins(36, 28, 36, 28)
        h.addWidget(self.body, 1)
        self.hide()
        parent.installEventFilter(self)

    def item(self, text, icon_name, fn, close=True):
        b = QPushButton(text)
        b.setObjectName("bs_item")
        b.setIcon(icon(icon_name, 20, dark=True))
        b.setIconSize(QSize(20, 20))
        b.clicked.connect(lambda: (self.hide_stage() if close else None, fn()))
        self.nv.addWidget(b)
        return b

    def spacer(self):
        self.nv.addStretch(1)

    def set_body(self, w):
        while self.bl.count():
            it = self.bl.takeAt(0)
            if it.widget():
                it.widget().setParent(None)
        self.bl.addWidget(w)

    def show_stage(self):
        p = self.parentWidget()
        self.setGeometry(p.rect())
        self.raise_()
        self.show()
        self.setFocus()

    def hide_stage(self):
        self.hide()
        self.closed.emit()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.hide_stage()
        else:
            super().keyPressEvent(e)

    def eventFilter(self, obj, e):
        if e.type() == QEvent.Type.Resize and self.isVisible():
            self.setGeometry(self.parentWidget().rect())
        return False
