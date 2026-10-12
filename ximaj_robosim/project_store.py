"""Validierung und atomare Projektdateien ohne GUI oder Skriptausführung."""
from pathlib import Path
import json
import math
import os
import shutil
import tempfile


def _vector(value, length, label, positive=False):
    if not isinstance(value, (list, tuple)) or len(value) != length:
        raise ValueError(f'{label}: {length} Zahlen erforderlich')
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or
           (positive and x <= 0) for x in value):
        raise ValueError(f'{label}: ungültige Zahlen')


def validate_document(data):
    if not isinstance(data, dict):
        raise ValueError('Projekt muss ein JSON-Objekt sein')
    if data.get('format', 1) not in (1, 2):
        raise ValueError('Diese Projektversion wird nicht unterstützt')
    robots = data.get('robots') or [data]
    if not isinstance(robots, list) or not robots:
        raise ValueError('Projekt enthält keine Roboterliste')
    scene = data.get('scene', [])
    if not isinstance(scene, list):
        raise ValueError('Szene muss eine Liste sein')
    for i, r in enumerate(robots):
        if not isinstance(r, dict):
            raise ValueError(f'Roboter {i + 1}: ungültiger Eintrag')
        for key in ('root', 'base', 'q'):
            if key in r:
                _vector(r[key], 6, f'Roboter {i + 1} / {key}')
        if not isinstance(r.get('program', ''), str):
            raise ValueError('Roboterprogramm muss Text sein')
        tool = r.get('tool', {})
        if not isinstance(tool, dict):
            raise ValueError('Werkzeug muss ein Objekt sein')
        if 'tcp' in tool:
            _vector(tool['tcp'], 6, 'Werkzeug-TCP')
    for i, o in enumerate(scene):
        if not isinstance(o, dict) or not isinstance(o.get('name'), str) or not o.get('kind'):
            raise ValueError(f'Szenenobjekt {i + 1}: Name und Art erforderlich')
        for key in ('pos', 'rot', 'size'):
            if key in o:
                _vector(o[key], 3, o['name'] + ' / ' + key, positive=(key == 'size'))
    names = {o['name'] for o in scene}
    parents = {o['name']: o.get('parent') for o in scene}
    for name in names:
        seen, node = set(), name
        while node in parents:
            if node in seen:
                raise ValueError('Zyklische Objekthierarchie: ' + name)
            seen.add(node)
            node = parents[node]
    for link in data.get('links', []):
        if not isinstance(link, dict) or any(not isinstance(link.get(k), (list, tuple)) or
             len(link[k]) != 2 or not all(isinstance(x, str) for x in link[k]) for k in ('src', 'dst')):
            raise ValueError('Ungültige Signalverbindung')
    active = data.get('active', 0)
    if not isinstance(active, int) or not 0 <= active < len(robots):
        raise ValueError('Aktiver Roboter liegt außerhalb der Roboterliste')
    return data


def read_project(path):
    with Path(path).open(encoding='utf-8-sig') as f:
        return validate_document(json.load(f))


def atomic_json(path, data, backup=False, validate=False):
    path = Path(path)
    if validate:
        validate_document(data)
    raw = json.dumps(data, ensure_ascii=False, indent=1, allow_nan=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        if backup and path.exists():
            backup_path = path.with_name(path.name + '.bak')
            # Auch die Sicherung wird erst nach vollständigem Kopieren ersetzt.
            backup_tmp = Path(tmp + '.bak')
            try:
                shutil.copy2(path, backup_tmp)
                os.replace(backup_tmp, backup_path)
            finally:
                backup_tmp.unlink(missing_ok=True)
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def write_project(path, data):
    atomic_json(path, data, backup=True, validate=True)
