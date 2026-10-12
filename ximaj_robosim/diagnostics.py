"""Nachvollziehbare Zellenprüfung. Prüft Daten; führt keine Programme aus."""
from collections import Counter
from dataclasses import dataclass, asdict
from pathlib import Path
import re
import math
from xrl import Interp, XrlError


@dataclass(frozen=True)
class Issue:
    level: str
    component: str
    message: str
    action: str
    line: int = 0


def inspect_cell(sim):
    issues = []
    def add(level, name, msg, action, line=0):
        issues.append(Issue(level, name, msg, action, line))
    names = [o.name for o in sim.scene] + [r.name for r in sim.robots]
    for name, count in Counter(names).items():
        if count > 1:
            add('Fehler', name, f'Name kommt {count} Mal vor', 'Eindeutigen Namen vergeben; Verbindungen und OPC-UA-Adressen benötigen ihn.')
    available = set(names)
    for link in sim.links:
        for kind in ('src', 'dst'):
            endpoint = link.get(kind, ())
            if len(endpoint) != 2 or endpoint[0] not in available:
                add('Fehler', 'E/A-Verbindung', f'Endpunkt fehlt: {endpoint}', 'Verbindung im Verschaltungseditor neu zuordnen.')
    incoming = Counter(tuple(x['dst']) for x in sim.links if 'dst' in x)
    for endpoint, count in incoming.items():
        if count > 1:
            add('Hinweis', endpoint[0], f'{count} Quellen auf {endpoint[1]} werden mit ODER verknüpft', 'Prüfen, ob die gemeinsame Ansteuerung gewollt ist.')
    for o in sim.scene:
        if any(not math.isfinite(float(v)) or float(v) <= 0 for v in o.size):
            add('Fehler', o.name, 'Ungültige Bauteilgröße', 'Drei positive Größen in mm einstellen.')
        if o.mesh_path and not Path(o.mesh_path).is_file():
            add('Warnung', o.name, 'CAD-Datei fehlt: ' + o.mesh_path, 'Datei erneut zuweisen; angezeigt wird gegebenenfalls ein Platzhalter.')
        if o.kind in ('sensor', 'color_sensor') and not (o.io or o.detected or o.color_outs):
            add('Warnung', o.name, 'Sensor hat kein zugeordnetes Signal', 'Eingang oder Signalverbindung zuweisen.')
        if o.parent and not (o.parent in available or o.parent.startswith('robot:')):
            add('Warnung', o.name, 'Übergeordnetes Objekt fehlt', 'Hierarchie prüfen; aktuelle Weltpose bleibt erhalten.')
    for r in sim.robots:
        src = r.src
        if r.mode == 'statements':
            import statements
            errors = statements.validate(r.statements)
            for msg in errors:
                add('Fehler', r.name, msg, 'Statement korrigieren.')
            if errors:
                continue
            try:
                src = statements.generate(r.statements, 'diagnose')[0]
            except (ValueError, TypeError, KeyError) as exc:
                add('Fehler', r.name, str(exc), 'Statement korrigieren.')
                continue
        try:
            p = Interp(src, r.io, dict(r.sv), r.frame_tables())
            for warning in p.warnings[:50]:
                add('Warnung', r.name, warning, 'Importhinweis prüfen; nicht jede Herstelleranweisung wird simuliert.')
        except (XrlError, ValueError, TypeError) as exc:
            add('Fehler', r.name, 'Syntax: ' + str(exc), 'Programm im Editor korrigieren.', getattr(exc, 'line', 0))
        clean = '\n'.join(line.split(';', 1)[0] for line in src.splitlines())
        outputs = {int(x) for x in re.findall(r'\$OUT\s*\[\s*(\d+)\s*\]', clean, re.I)}
        for kind, text in re.findall(r'\$(IN|OUT)\s*\[\s*(\d+)\s*\]', clean, re.I):
            if not 0 < int(text) < r.io.N:
                add('Fehler', r.name, f'${kind}[{text}] liegt außerhalb der E/A', 'Signalnummer 1 bis 4096 verwenden.')
        if r.tool.grip_out and r.tool.grip_out not in outputs and any(o.graspable for o in sim.scene):
            add('Warnung', r.name, f'Greifer $OUT[{r.tool.grip_out}] wird im Programm nicht direkt verwendet', 'Greiferausgang und Programm vergleichen; SIGNAL-Aliase können ebenfalls schalten.')
        grip = r.gripper_info()
        if grip['conflicts']:
            add('Warnung', r.name, f'Greiferausgang {grip["output"]} steuert auch ' + ', '.join(grip['conflicts']), 'Getrennte Ausgänge verwenden, wenn die Funktionen unabhängig sind.')
        for name, count in Counter(p.get('name', '') for p in r.waypoints).items():
            if count > 1:
                add('Warnung', r.name, f'Punktname {name} kommt mehrfach vor', 'Eindeutige Punktnamen vergeben.')
    return issues


def signal_rows(sim):
    """Istwerte und beteiligte Endpunkte statt erfundener Signalzustände."""
    return [{'source': ' / '.join(link['src']), 'target': ' / '.join(link['dst']),
             'value': bool(sim._source_signal(link['src']))} for link in sim.links]


def export_report(path, sim, clients=()):
    from project_store import atomic_json
    report = {'version': '2.0.0', 'simulation_time_s': sim.t, 'project': sim.to_dict(),
              'issues': [asdict(i) for i in inspect_cell(sim)], 'signals': signal_rows(sim),
              'clients': [{'name': c.name, 'status': c.status, 'error': c.error,
                           'connected': c.connected, 'writes_armed': c.writes_armed,
                           'mapping_errors': [m.get('error') for m in c.mappings]} for c in clients]}
    atomic_json(path, report)
