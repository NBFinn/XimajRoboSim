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

try:
    from asyncua import Client, ua
    AVAILABLE = True
except Exception:
    AVAILABLE = False

TARGET_HELP = ("IN:n  = Robotereingang $IN[n]\nOUT:n = Roboterausgang $OUT[n]\nOVERRIDE = Override in %\n"
               "SPEED = Simulationsgeschwindigkeit\nAXIS:<Roboter>:<1-6> = Achswinkel (nur schreiben)\n"
               "TCP:<Roboter>:<X|Y|Z|A|B|C> = TCP-Position (nur schreiben)\nSTATE:<Roboter> = Zustand (nur schreiben)")


def _sim_value(sim, target):
    """Wert eines Simulationsziels lesen"""
    t = target.strip().upper()
    if t.startswith("IN:"):
        return bool(sim.io.get_in(int(t[3:])))
    if t.startswith("OUT:"):
        return bool(sim.io.get_out(int(t[4:])))
    if t == "OVERRIDE":
        return float(sim.override * 100.0)
    if t == "SPEED":
        return float(sim.speed_factor)
    parts = target.split(":")
    if len(parts) >= 2:
        r = next((r for r in sim.robots if r.name.upper() == parts[1].strip().upper()), sim.active)
        if parts[0].upper() == "AXIS" and len(parts) == 3:
            return float(r.q[int(parts[2]) - 1])
        if parts[0].upper() == "TCP" and len(parts) == 3:
            return float(r.sv.get("POS_ACT", [0] * 6)["XYZABC".index(parts[2].strip().upper())])
        if parts[0].upper() == "STATE":
            return str(r.state)
    raise ValueError(f"Unbekanntes Ziel: {target}")


def _set_sim(sim, target, value):
    """Wert in die Simulation schreiben"""
    t = target.strip().upper()
    if t.startswith("IN:"):
        sim.io.set_in(int(t[3:]), bool(value))
    elif t.startswith("OUT:"):
        sim.io.set_out(int(t[4:]), bool(value))
    elif t == "OVERRIDE":
        sim.override = max(0.0, min(1.0, float(value) / 100.0))
    elif t == "SPEED":
        if float(value) > 0:
            sim.speed_factor = float(value)
    else:
        raise ValueError(f"Ziel {target} kann nicht gelesen werden (nur schreiben)")


class ClientLink:
    def __init__(self, sim, url="opc.tcp://localhost:4840", name="Verbindung", user="", password="", mappings=None,
                 period=0.1):
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

    def to_dict(self):
        return {"name": self.name, "url": self.url, "user": self.user, "mappings": self.mappings, "period": self.period}

    @staticmethod
    def from_dict(sim, d):
        return ClientLink(sim, d.get("url", ""), d.get("name", "Verbindung"), d.get("user", ""), "",
                          d.get("mappings", []), d.get("period", 0.1))

    def _client(self):
        c = Client(self.url, timeout=4)
        if self.user:
            c.set_user(self.user)
            c.set_password(self.password)
        return c

    # ------------------------------------------------------------------ Verbinden
    def connect(self):
        if not AVAILABLE:
            self.error = "Paket 'asyncua' fehlt"
            return False
        if self.connected:
            return True
        self._stop.clear()
        self.error = ""
        self.status = "verbinde …"
        self.thread = threading.Thread(target=lambda: asyncio.run(self._run()), daemon=True)
        self.thread.start()
        t0 = time.time()
        while not self.connected and not self.error and time.time() - t0 < 8:
            time.sleep(0.05)
        return self.connected

    def disconnect(self):
        self._stop.set()
        if self.thread:
            self.thread.join(timeout=5)
        self.connected = False
        self.status = "getrennt"

    async def _run(self):
        try:
            async with self._client() as c:
                self.connected = True
                self.status = "verbunden"
                nodes = {}
                last = {}
                while not self._stop.is_set():
                    for m in list(self.mappings):
                        nid = m.get("node", "")
                        try:
                            node = nodes.get(nid) or c.get_node(nid)
                            nodes[nid] = node
                            if m.get("dir", "read") == "read":
                                v = await node.read_value()
                                self.values[nid] = v
                                if last.get(nid, object()) != v:          # nur Aenderungen uebernehmen
                                    _set_sim(self.sim, m["target"], v)
                                    last[nid] = v
                            else:
                                v = _sim_value(self.sim, m["target"])
                                if last.get(nid, object()) != v:
                                    vt = await node.read_data_type_as_variant_type()
                                    await node.write_value(ua.DataValue(ua.Variant(_cast(v, vt), vt)))
                                    last[nid] = v
                                self.values[nid] = v
                            m.pop("error", None)
                        except Exception as e:
                            m["error"] = f"{type(e).__name__}: {e}"
                    await asyncio.sleep(self.period)
        except Exception as e:
            self.error = f"{type(e).__name__}: {e}"
            self.status = "Fehler"
        finally:
            self.connected = False
            if self.status != "Fehler":
                self.status = "getrennt"

    # ------------------------------------------------------------------ Durchsuchen
    def browse(self, max_depth=6, max_nodes=3000):
        """Variablen des Servers: Liste (Pfad, NodeId, Datentyp, Wert); blockiert bis fertig"""
        if not AVAILABLE:
            raise RuntimeError("Paket 'asyncua' fehlt")
        return asyncio.run(self._browse(max_depth, max_nodes))

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
    if n == "Boolean":
        return bool(v)
    if n in ("Float", "Double"):
        return float(v)
    if n in ("SByte", "Byte", "Int16", "UInt16", "Int32", "UInt32", "Int64", "UInt64"):
        return int(round(float(v))) if not isinstance(v, bool) else int(v)
    return str(v)
