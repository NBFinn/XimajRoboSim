"""OPC-UA-Client der Ximaj RoboSim: Verbindung zu externen Servern (SPS, Leitsystem, Robotersteuerung)
und Kopplung ihrer Variablen mit Signalen der Simulation.

Eine Verbindung (ClientLink) hat eine URL, optional Benutzer/Passwort und eine Liste von Zuordnungen:
  {"node": "ns=3;s=Start", "dir": "read"|"write", "target": "IN:5" | "OUT:3" | "SPEED" | "OVERRIDE"}
  read  : Wert des externen Knotens -> Simulation (Eingang/Ausgang setzen, Geschwindigkeit, Override)
  write : Wert aus der Simulation -> externer Knoten (Ausgang/Eingang, Roboterachse "AXIS:Roboter:1", TCP "TCP:Roboter:X")
"""
import asyncio
import threading
import time
import math
import re
from kinematics import mat_to_pose

try:
    from asyncua import Client, ua
    AVAILABLE = True
except Exception:
    AVAILABLE = False

TARGET_HELP = ("IN:n  = Robotereingang $IN[n]\nOUT:n = Roboterausgang $OUT[n]\nOVERRIDE = Override in %\n"
               "SPEED = Simulationsgeschwindigkeit\nAXIS:<Roboter>:<1-6> = Achswinkel (nur schreiben)\n"
               "TCP:<Roboter>:<X|Y|Z|A|B|C> = TCP-Position (nur schreiben)\nSTATE:<Roboter> = Zustand (nur schreiben)")
TARGET_HELP += ('\nJOINTS:<Roboter> = sechs Achsen als Array (nur schreiben)\n'
                'POSE:<Roboter>:BASE|WORLD = TCP-Pose als Array (nur schreiben)\n'
                'NodeIds mit nsu=<Namespace-URI>;s=<Identifier> werden beim Verbinden aufgelöst.')


def _io_number(text):
    n = int(text)
    if not 1 <= n <= 4096:
        raise ValueError('Signalnummer muss zwischen 1 und 4096 liegen')
    return n


def _boolean(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and math.isfinite(value):
        return value != 0
    if isinstance(value, str) and value.casefold() in ('true', 'false', '0', '1'):
        return value.casefold() in ('true', '1')
    raise ValueError('Signal benötigt Boolean, 0/1 oder TRUE/FALSE')


def _sim_value(sim, target):
    """Wert eines Simulationsziels lesen"""
    t = target.strip().upper()
    if t.startswith("IN:"):
        return bool(sim.io.get_in(_io_number(t[3:])))
    if t.startswith("OUT:"):
        return bool(sim.io.get_out(_io_number(t[4:])))
    if t == "OVERRIDE":
        return float(sim.override * 100.0)
    if t == "SPEED":
        return float(sim.speed_factor)
    parts = target.split(":")
    if len(parts) >= 2:
        r = next((r for r in sim.robots if r.name.upper() == parts[1].strip().upper()), None)
        if r is None:
            raise ValueError('Roboter nicht vorhanden: ' + parts[1])
        if parts[0].upper() == "AXIS" and len(parts) == 3:
            n = int(parts[2])
            if not 1 <= n <= 6:
                raise ValueError('Achse muss zwischen 1 und 6 liegen')
            return float(r.q[n - 1])
        if parts[0].upper() == "TCP" and len(parts) == 3:
            return float(mat_to_pose(r.tcp_in_base())["XYZABC".index(parts[2].strip().upper())])
        if parts[0].upper() == "STATE":
            return str(r.state)
        if parts[0].upper() == 'JOINTS' and len(parts) == 2:
            return list(map(float, r.q))
        if parts[0].upper() == 'POSE' and len(parts) == 3 and parts[2].upper() in ('BASE', 'WORLD'):
            return list(map(float, mat_to_pose(r.tcp_world() if parts[2].upper() == 'WORLD' else r.tcp_in_base())))
    raise ValueError(f"Unbekanntes Ziel: {target}")


def _set_sim(sim, target, value):
    """Wert in die Simulation schreiben"""
    t = target.strip().upper()
    if t.startswith("IN:"):
        sim.io.set_in(_io_number(t[3:]), _boolean(value))
    elif t.startswith("OUT:"):
        sim.io.set_out(_io_number(t[4:]), _boolean(value))
    elif t == "OVERRIDE":
        value = float(value)
        if not math.isfinite(value):
            raise ValueError('Override ist nicht endlich')
        sim.override = max(0.0, min(1.0, value / 100.0))
    elif t == "SPEED":
        value = float(value)
        if not math.isfinite(value) or value <= 0:
            raise ValueError('Geschwindigkeit muss endlich und größer als 0 sein')
        sim.speed_factor = value
    else:
        raise ValueError(f"Ziel {target} kann nicht gelesen werden (nur schreiben)")


class ClientLink:
    def __init__(self, sim, url="opc.tcp://localhost:4840", name="Verbindung", user="", password="", mappings=None,
                 period=0.1, reconnect=True):
        self.sim = sim
        self.url = url
        self.name = name
        self.user = user
        self.password = password
        self.mappings = list(mappings or [])
        self.period = float(period)
        self.connected = False
        self.error = ""
        self.status = "getrennt"
        self.values = {}            # node -> zuletzt gelesener/geschriebener Wert
        self._stop = threading.Event()
        self.thread = None
        self.reconnect = bool(reconnect)
        self.writes_armed = True
        self.reconnects = 0
        self.last_success = 0.
        self._lifecycle = threading.Lock()

    def to_dict(self):
        return {"name": self.name, "url": self.url, "user": self.user,
                "mappings": [{k: m[k] for k in ('node', 'dir', 'target') if k in m} for m in self.mappings],
                "period": self.period, 'reconnect': self.reconnect}

    @staticmethod
    def from_dict(sim, d):
        return ClientLink(sim, d.get("url", ""), d.get("name", "Verbindung"), d.get("user", ""), "",
                          d.get("mappings", []), d.get("period", 0.1), d.get('reconnect', True))

    def _client(self):
        c = Client(self.url, timeout=4)
        if self.user:
            c.set_user(self.user)
            c.set_password(self.password)
        return c

    # ------------------------------------------------------------------ Verbinden
    def connect(self, wait=True):
        if not AVAILABLE:
            self.error = "Paket 'asyncua' fehlt"
            return False
        if not self.url.startswith('opc.tcp://') or not math.isfinite(self.period) or self.period < .02:
            self.error = 'OPC-UA-URL und Abfragezyklus prüfen'
            return False
        with self._lifecycle:
            if self.thread and self.thread.is_alive():
                if self._stop.is_set():
                    self.error = 'Die vorherige Verbindung wird noch beendet'
                    return False
                return self.connected if wait else True
            self._stop.clear()
            self.error = ""
            self.status = "verbinde …"
            self.thread = threading.Thread(target=lambda: asyncio.run(self._run()), daemon=True)
            self.thread.start()
        if not wait:
            return True
        t0 = time.time()
        while not self.connected and not self.error and time.time() - t0 < 8:
            time.sleep(0.05)
        return self.connected

    def disconnect(self, wait=True):
        self._stop.set()
        self.writes_armed = False
        if self.thread and wait:
            self.thread.join(timeout=5)
        self.connected = False
        self.status = "getrennt"

    def arm_writes(self):
        if not self.connected:
            raise ValueError('Zuerst eine Verbindung herstellen')
        self.writes_armed = True

    async def _sleep(self, seconds):
        end = time.monotonic() + seconds
        while not self._stop.is_set() and time.monotonic() < end:
            await asyncio.sleep(min(.1, max(0., end - time.monotonic())))

    async def _node(self, c, nid):
        match = re.fullmatch(r'nsu=(.+);([isgb])=(.*)', nid)
        if match:
            index = await c.get_namespace_index(match[1])
            nid = f'ns={index};{match[2]}={match[3]}'
        return c.get_node(nid)

    async def _run(self):
        delay = .25
        while not self._stop.is_set():
            try:
                await self._session()
                break
            except Exception as e:
                self.connected = False
                self.writes_armed = False
                self.error = f'{type(e).__name__}: {e}'
                if not self.reconnect:
                    self.status = 'Fehler'
                    break
                self.reconnects += 1
                self.status = f'Wiederverbinden in {delay:.2f} s · Schreiben gesperrt'
                await self._sleep(delay)
                delay = min(30., delay * 2)
        self.connected = False
        if self._stop.is_set():
            self.status = 'getrennt'

    async def _session(self):
            async with self._client() as c:
                self.connected = True
                self.error = ''
                self.status = "verbunden"
                nodes = {}
                types = {}
                last = {}
                while not self._stop.is_set():
                    await c.check_connection()
                    reads = []
                    for m in list(self.mappings):
                        if self._stop.is_set():
                            break
                        nid = m.get("node", "")
                        try:
                            node = nodes.get(nid) or await self._node(c, nid)
                            nodes[nid] = node
                            key = (m.get('dir', 'read'), nid, m['target'])
                            if m.get("dir", "read") == "read":
                                reads.append((m, node, key))
                            else:
                                if m.get('dir') != 'write':
                                    raise ValueError('Richtung muss read oder write sein')
                                if not self.writes_armed:
                                    m['error'] = 'Schreiben nach Verbindungsabbruch gesperrt; ausdrücklich freigeben'
                                    continue
                                v = _sim_value(self.sim, m["target"])
                                if last.get(key, object()) != v:
                                    vt = types.get(nid) or await node.read_data_type_as_variant_type()
                                    types[nid] = vt
                                    await node.write_value(ua.DataValue(ua.Variant(_cast(v, vt), vt)))
                                    last[key] = v
                                self.values[nid] = v
                            m.pop("error", None)
                        except Exception as e:
                            m["error"] = f"{type(e).__name__}: {e}"
                            if m.get('dir') == 'write':
                                self.writes_armed = False
                            if isinstance(e, (ConnectionError, OSError, asyncio.TimeoutError)):
                                self.writes_armed = False
                                raise
                    for offset in range(0, len(reads), 128):
                        batch = reads[offset:offset + 128]
                        values = await c.read_attributes([node for _, node, _ in batch])
                        for (m, node, key), data in zip(batch, values):
                            if self._stop.is_set():
                                break
                            try:
                                data.StatusCode.check()
                                v = data.Value.Value
                                self.values[m['node']] = v
                                if last.get(key, object()) != v:
                                    _set_sim(self.sim, m['target'], v)
                                    last[key] = v
                                m.pop('error', None)
                            except Exception as exc:
                                m['error'] = f'{type(exc).__name__}: {exc}'
                    self.last_success = time.monotonic()
                    self.status = 'verbunden' + ('' if self.writes_armed else ' · Schreiben gesperrt')
                    await self._sleep(self.period)

    # ------------------------------------------------------------------ Durchsuchen
    def browse(self, max_depth=6, max_nodes=3000):
        """Variablen des Servers: Liste (Pfad, NodeId, Datentyp, Wert); blockiert bis fertig"""
        if not AVAILABLE:
            raise RuntimeError("Paket 'asyncua' fehlt")
        return asyncio.run(asyncio.wait_for(self._browse(max_depth, max_nodes), timeout=30.))

    async def _browse(self, max_depth, max_nodes):
        out = []
        async with self._client() as c:
            async def walk(node, path, depth):
                if depth > max_depth or len(out) >= max_nodes:
                    return
                for ch in await node.get_children():
                    try:
                        bn = (await ch.read_browse_name()).Name
                        cls = await ch.read_node_class()
                    except Exception:
                        continue
                    p = f"{path}/{bn}" if path else bn
                    if cls == ua.NodeClass.Variable:
                        try:
                            v = await ch.read_value()
                            vt = (await ch.read_data_type_as_variant_type()).name
                        except Exception:
                            v, vt = None, "?"
                        out.append((p, ch.nodeid.to_string(), vt, v))
                    elif cls == ua.NodeClass.Object and not (depth == 0 and bn == "Server"):
                        await walk(ch, p, depth + 1)

            await walk(c.nodes.objects, "", 0)
        return out


def _cast(v, vt):
    """Simulationswert in den Datentyp des Zielknotens umwandeln"""
    n = vt.name
    if isinstance(v, (list, tuple)):
        return [_cast(x, vt) for x in v]
    if n == "Boolean":
        return _boolean(v)
    if n in ("Float", "Double"):
        value = float(v)
        if not math.isfinite(value):
            raise ValueError('Nicht-endlicher Zahlenwert')
        return value
    if n in ("SByte", "Byte", "Int16", "UInt16", "Int32", "UInt32", "Int64", "UInt64"):
        value = int(v) if isinstance(v, (int, bool)) else int(round(float(v)))
        bits = {'SByte': 8, 'Byte': 8, 'Int16': 16, 'UInt16': 16, 'Int32': 32, 'UInt32': 32, 'Int64': 64, 'UInt64': 64}[n]
        signed = n.startswith('Int') or n == 'SByte'
        lo, hi = (-2**(bits - 1), 2**(bits - 1) - 1) if signed else (0, 2**bits - 1)
        if not lo <= value <= hi:
            raise ValueError(f'Wert außerhalb {n}')
        return value
    return str(v)
