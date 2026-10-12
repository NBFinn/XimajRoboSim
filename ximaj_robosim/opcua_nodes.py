"""Feste OPC-UA-Adressen und Export der tatsächlich vorhandenen Serverknoten."""
import csv
import json
import math
import os
import tempfile
from pathlib import Path
from urllib.parse import quote

NAMESPACE_URI = "urn:ximaj:robosim"
ROOT_ID = "XimajRoboSim"


def child_id(parent_id, name):
    # Trennzeichen und Prozentzeichen in Namen dürfen keinen zweiten Pfad erzeugen.
    return parent_id + "/" + quote(str(name), safe="")


def json_value(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (list, tuple)):
        return [json_value(v) for v in value]
    return value


def export_nodes(path, rows, endpoints):
    """Atomar schreiben; eine fehlgeschlagene Ausgabe ersetzt keine vorhandene Datei."""
    path = Path(path)
    fd, temp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8-sig" if path.suffix.lower() == ".csv" else "utf-8", newline="") as f:
            if path.suffix.lower() == ".csv":
                fields = ["path", "node_id", "namespace_uri", "identifier", "node_class", "data_type", "access", "unit", "frame", "value"]
                writer = csv.DictWriter(f, fieldnames=fields, delimiter=";", extrasaction="ignore")
                writer.writeheader()
                for row in rows:
                    writer.writerow({**row, "value": json.dumps(json_value(row.get("value")), ensure_ascii=False, allow_nan=False)})
            else:
                json.dump({"namespace_uri": NAMESPACE_URI, "endpoints": endpoints,
                           "nodes": [{**r, "value": json_value(r.get("value"))} for r in rows]},
                          f, indent=2, ensure_ascii=False, allow_nan=False)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
