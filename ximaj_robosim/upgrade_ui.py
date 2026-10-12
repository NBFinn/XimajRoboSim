"""Produktionscockpit, Debugger und explizite Befehlsauswahl für RoboSim 2."""
from dataclasses import asdict
import json
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QColor
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QTableWidget,
                            QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox, QComboBox, QDialog,
                            QListWidget, QListWidgetItem, QSplitter, QAbstractItemView, QGroupBox, QGridLayout, QScrollArea)
from diagnostics import inspect_cell, signal_rows, export_report


def table(headers, name):
    t = QTableWidget(0, len(headers))
    t.setObjectName(name)
    t.setHorizontalHeaderLabels(headers)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    t.horizontalHeader().setStretchLastSection(True)
    t.setAlternatingRowColors(True)
    t.setMinimumSize(160, 100)
    t.verticalHeader().hide()
    return t


def fill(t, rows):
    t.setUpdatesEnabled(False)
    t.setRowCount(len(rows))
    for row, cells in enumerate(rows):
        for col, value in enumerate(cells):
            text = str(value)
            item = QTableWidgetItem(text)
            item.setToolTip(text)
            t.setItem(row, col, item)
    t.setUpdatesEnabled(True)


class Cockpit(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win, self.issues = win, []
        self.setObjectName('productionCockpit')
        layout = QVBoxLayout(self)
        self.summary = QLabel('Zelle prüfen, bevor du den Ablauf startest.')
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        controls = QGridLayout()
        check = QPushButton('Zelle prüfen')
        check.clicked.connect(self.check)
        controls.addWidget(check, 0, 0)
        export = QPushButton('Diagnosebericht exportieren …')
        export.clicked.connect(self.export)
        controls.addWidget(export, 0, 1)
        self.profile = QComboBox()
        self.profile.addItems(['Ausgewogen · 60 Bilder/s', 'Große Zellen · 30 Bilder/s'])
        self.profile.setAccessibleName('Leistungsprofil')
        self.profile.setCurrentIndex(int(win.settings.get('performance_profile', 0)) if win.settings.get('performance_profile', 0) in (0, 1) else 0)
        self.profile.currentIndexChanged.connect(self.apply_profile)
        controls.addWidget(self.profile, 1, 0, 1, 2)
        layout.addLayout(controls)
        self.perf = QLabel()
        self.perf.setWordWrap(True)
        layout.addWidget(self.perf)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText('Diagnose und Signalverbindungen filtern …')
        self.filter.setAccessibleName('Diagnosefilter')
        self.filter.textChanged.connect(self.filter_rows)
        layout.addWidget(self.filter)
        split = QSplitter(Qt.Orientation.Vertical)
        self.findings = table(['Stufe', 'Komponente', 'Beobachtung', 'Nächster Test / Maßnahme'], 'cellFindings')
        self.findings.setColumnWidth(0, 80)
        self.findings.setColumnWidth(1, 150)
        self.findings.setColumnWidth(2, 370)
        self.findings.cellDoubleClicked.connect(self.navigate)
        split.addWidget(self.findings)
        self.signals = table(['Quelle', 'Ziel', 'Istwert'], 'liveSignals')
        self.signals.setColumnWidth(0, 360)
        self.signals.setColumnWidth(1, 360)
        split.addWidget(self.signals)
        layout.addWidget(split, 1)
        self.apply_profile(self.profile.currentIndex())

    def apply_profile(self, index):
        self.win.settings['performance_profile'] = index
        self.win.timer.setInterval(33 if index else 16)
        self.win.sim.frame_budget_ms = 12.

    def check(self):
        self.issues = inspect_cell(self.win.sim)
        fill(self.findings, [(i.level, i.component, i.message, i.action) for i in self.issues])
        errors = sum(i.level == 'Fehler' for i in self.issues)
        warnings = sum(i.level == 'Warnung' for i in self.issues)
        self.summary.setText(f'{len(self.win.sim.robots)} Roboter · {len(self.win.sim.scene)} Komponenten · '
                             f'{errors} Fehler · {warnings} Warnungen. Doppelklick führt zur betroffenen Programmzeile.')
        self.filter_rows()
        return errors == 0

    def navigate(self, row, col):
        if not 0 <= row < len(self.issues):
            return
        issue = self.issues[row]
        if issue.line and issue.component == self.win.sim.active.name:
            self.win.bottom.setCurrentIndex(1)
            self.win.goto_line(issue.line)

    def filter_rows(self):
        needle = self.filter.text().casefold()
        for t in (self.findings, self.signals):
            for row in range(t.rowCount()):
                t.setRowHidden(row, not any(needle in t.item(row, col).text().casefold() for col in range(t.columnCount()) if t.item(row, col)))

    def refresh(self):
        s = self.win.sim
        waiting = [(r.name, max(0., s.t - r.wait_started)) for r in s.robots
                   if r.state == 'wait' and r.wait_fn and r.wait_started is not None]
        p = s.performance
        self.perf.setText(f"Simulationsschritt: {p['step_ms']:.1f} ms · {p['substeps']} Teilschritte · "
                          f"Zeit im Rückstand: {p['backlog_s']:.3f} s · {len(s.scene)} Objekte" +
                          (' · Warten auf E/A: ' + ', '.join(f'{n} ({t:.1f} s)' for n, t in waiting) if waiting else ''))
        if self.isVisible():
            fill(self.signals, [(r['source'], r['target'], 'EIN' if r['value'] else 'AUS') for r in signal_rows(s)])
            self.filter_rows()

    def export(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Diagnose exportieren', 'RoboSim-Diagnose.json', 'JSON (*.json)')
        if path:
            try:
                export_report(path, self.win.sim, self.win.opc_clients)
            except (OSError, ValueError, TypeError) as exc:
                QMessageBox.warning(self, 'Diagnose', str(exc))


class Debugger(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setObjectName('programDebugger')
        l = QVBoxLayout(self)
        self.status = QLabel()
        self.status.setWordWrap(True)
        l.addWidget(self.status)
        controls = QGridLayout()
        for index, (text, fn) in enumerate([('Weiter (F5)', win.run_prog), ('Schritt (F10)', win.step_prog), ('Pause', win.sim.pause_all),
                         ('Haltepunkt (F9)', lambda: win.editor.toggle()), ('Haltepunkte entfernen', self.clear)]):
            b = QPushButton(text)
            b.clicked.connect(fn)
            controls.addWidget(b, index // 3, index % 3)
        l.addLayout(controls)
        hint = QLabel('Haltepunkte halten vor der Anweisung die ganze Zelle an. Nach Textänderungen Zeilennummern prüfen. Werte werden nur beobachtet.')
        hint.setWordWrap(True)
        l.addWidget(hint)
        self.variables = table(['Bereich / Name', 'Wert'], 'debugVariables')
        self.variables.setColumnWidth(0, 280)
        l.addWidget(self.variables, 1)

    def clear(self):
        self.win.sim.active.breakpoints.clear()
        self.win.editor.gutter.update()
        self.win.mark_changed()

    def refresh(self):
        r = self.win.sim.active
        stack = ' → '.join(n for n, _ in r.interp.frames) if r.interp else 'kein laufendes Programm'
        self.status.setText(f'{r.name} · {r.state} · Zeile {r.cur_line} · Aufruf: {stack} · '
                            'Haltepunkte: ' + (', '.join(map(str, sorted(r.breakpoints))) or 'keine'))
        if not self.isVisible():
            return
        values = r.interp.debug_variables() if r.interp else {}
        rows = [(name, repr(value)[:700]) for name, value in sorted(values.items())]
        rows += [('$' + name, repr(value)[:700]) for name, value in sorted(r.sv.items())]
        fill(self.variables, rows[:500])


def command_palette(win, text=''):
    dialog = QDialog(win)
    dialog.setWindowTitle('Befehl auswählen · Strg+K')
    dialog.resize(760, 510)
    l = QVBoxLayout(dialog)
    query = QLineEdit(text)
    query.setPlaceholderText('Befehl oder Bereich eingeben …')
    query.setAccessibleName('Befehlssuche')
    l.addWidget(query)
    choices = QListWidget()
    l.addWidget(choices, 1)
    info = QLabel('Befehl auswählen und mit Eingabe oder Doppelklick ausführen.')
    l.addWidget(info)
    entries = []
    for title, page in win.ribbon.rb.pages.items():
        for group, g in page.groups.items():
            for name, button in g.items.items():
                if hasattr(button, 'click'):
                    entries.append((f'{title} › {group} › {name.replace(chr(10), " ")}', title, button))
    def search():
        choices.clear()
        tokens = query.text().casefold().split()
        for name, title, button in entries:
            if all(t in name.casefold() for t in tokens):
                item = QListWidgetItem(name)
                item.setData(Qt.ItemDataRole.UserRole, (title, button))
                if not button.isEnabled():
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                choices.addItem(item)
        choices.setCurrentRow(0)
    def execute(item=None):
        item = item or choices.currentItem()
        if item:
            title, button = item.data(Qt.ItemDataRole.UserRole)
            if button.isEnabled():
                dialog.accept()
                win.ribbon.rb.select(title)
                button.click()
    query.textChanged.connect(search)
    query.returnPressed.connect(lambda: execute())
    choices.itemDoubleClicked.connect(execute)
    search()
    query.setFocus()
    dialog.exec()


def install(win):
    win.cockpit = Cockpit(win)
    win.debugger = Debugger(win)
    def page(widget, name):
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QScrollArea.Shape.NoFrame)
        area.setWidget(widget)
        return win.bottom.addTab(area, name)
    win.cockpit_index = page(win.cockpit, 'Produktionscockpit')
    win.debugger_index = page(win.debugger, 'Debugger')
    win.bottom.setUsesScrollButtons(True)
    for name, shortcut, fn in [('Befehlspalette', 'Ctrl+K', lambda: command_palette(win)),
                               ('Haltepunkt', 'F9', lambda: win.editor.toggle()),
                               ('Zelle prüfen', 'Ctrl+Shift+D', win.open_cockpit)]:
        action = QAction(name, win)
        action.setShortcut(shortcut)
        action.triggered.connect(fn)
        win.addAction(action)
    win.upgrade_timer = QTimer(win)
    win.upgrade_timer.timeout.connect(lambda: (win.cockpit.refresh(), win.debugger.refresh()))
    win.upgrade_timer.start(250)


def client_diagnose(win, client, run=True):
    import time
    dialog = QDialog(win)
    dialog.setWindowTitle('OPC-UA-Live-Diagnose · ' + client.name)
    dialog.resize(1050, 530)
    l = QVBoxLayout(dialog)
    status = QLabel()
    status.setWordWrap(True)
    l.addWidget(status)
    t = table(['NodeId', 'Richtung', 'Simulationsziel', 'Letzter Wert', 'Zustand'], 'clientMappings')
    t.setColumnWidth(0, 300)
    t.setColumnWidth(2, 170)
    l.addWidget(t, 1)
    info = QLabel('Letzte Werte bleiben nach Abbruch sichtbar und gelten dann als veraltet. Schreiben erst nach Prüfung freigeben.')
    info.setWordWrap(True)
    l.addWidget(info)
    close = QPushButton('Schließen')
    close.clicked.connect(dialog.accept)
    l.addWidget(close)
    def refresh():
        age = max(0., time.monotonic() - client.last_success) if client.last_success else None
        status.setText(f'{client.status} · {client.reconnects} Wiederverbindungsversuche · '
                       f'Letzte erfolgreiche Abfrage: {age:.1f} s her' if age is not None else client.status + ' · noch keine erfolgreiche Abfrage')
        fill(t, [(m.get('node', ''), m.get('dir', 'read'), m.get('target', ''), repr(client.values.get(m.get('node')))[:250],
                  m.get('error') or ('aktuell' if client.connected else 'veraltet / nicht bestätigt')) for m in client.mappings])
    timer = QTimer(dialog)
    timer.timeout.connect(refresh)
    timer.start(250)
    dialog.finished.connect(timer.stop)
    refresh()
    if run:
        dialog.exec()
    return dialog
