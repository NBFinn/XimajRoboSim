"""OPC-UA-Server der Ximaj RoboSim (Bibliothek asyncua) - Anbindung an SPS, Leitsysteme und Tools.

Ist der gewuenschte Port belegt (z. B. 4840 durch einen anderen OPC-UA-Dienst), sucht der Server automatisch
den naechsten freien Port. Endpunkt: opc.tcp://<PC-Name>:<Port>/ximaj/robosim   Namespace: urn:ximaj:robosim

Knoten (unter Objects/XimajRoboSim):
  Simulation/  State, Time, SpeedFactor (rw), RobotCount; Methoden StartAll, StopAll, ResetAll
  Robots/<Name>/  State, Line, Message, Model, Override (rw), Collision, CycleTime, EnergyWh, E1,
                  Axes/A1..A6, Tcp/X,Y,Z,A,B,C, TcpWorld, Points/<Name>; Methoden Start, Stop, Pause, Reset, LoadProgram(text)
  Robot/        wie oben fuer den aktiven Roboter (kompatibel zu frueheren Versionen)
  IO/In/I1..In (rw)  IO/Out/O1..On (rw)   - Beschreibung = E/A-Name aus der Simulation
  Components/<Objekt>/  Sensor: Signal | Foerderer: Running, Speed (rw) | Erzeuger: Created |
                        Farbsensor: Detected, Color | Signalleuchte: Color
  Methoden am Wurzelknoten: Start, Stop, Pause, Reset, LoadProgram(text) (aktiver Roboter)
"""
import asyncio
import socket
import threading
import time
import math
import copy
from opcua_nodes import NAMESPACE_URI, ROOT_ID, child_id
from kinematics import mat_to_pose, pose_to_mat

try:
    from asyncua import Server, ua
    from asyncua.common.methods import uamethod
    AVAILABLE = True
except Exception:   # asyncua nicht installiert
    AVAILABLE = False

N_IO = 128


def port_free(port, host="0.0.0.0"):
    """True, wenn der TCP-Port auf diesem Rechner frei ist"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        s.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def port_owner(port):
    """Name des Prozesses, der den Port belegt (Windows: netstat/tasklist), sonst leer"""
    try:
        import subprocess, re, os
        flags = 0x08000000 if os.name == "nt" else 0          # CREATE_NO_WINDOW
        out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True, timeout=5,
                             encoding="oem" if os.name == "nt" else None, errors="replace",
                             creationflags=flags).stdout
        pid = next((ln.split()[-1] for ln in out.splitlines()
                    if re.search(rf":{port}\s", ln) and "LISTEN" in ln.upper() or re.search(rf":{port}\s.*ABH", ln)), None)
        if pid and pid.isdigit():
            t = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], capture_output=True, text=True,
                               encoding="oem" if os.name == "nt" else None, errors="replace",
                               timeout=5, creationflags=flags).stdout.strip()
            if t.startswith('"'):
                return t.split('","')[0].strip('"').replace(".exe", "")
    except Exception:
        pass
    return ""


class OpcUaService:
    def __init__(self, sim, port=4840, auto_port=True, local_only=False, n_io=N_IO):
        self.sim = sim
        self.port_wanted = int(port)
        self.port = int(port)
        self.auto_port = auto_port
        self.local_only = local_only
        self.n_io = int(n_io)
        self.running = False
        self.thread = None
        self.error = ""
        self.info = ""               # Hinweis, z. B. Portwechsel
        self.host = socket.gethostname()
        self.endpoint = f"opc.tcp://{self.host}:{port}/ximaj/robosim"
        self._stop = threading.Event()
        self.commands = []          # (Befehl, Argument, Robotername) - vom GUI-Thread abgearbeitet
        self.sessions = 0
        self.namespace_index = None
        self._catalog = {}
        self._catalog_lock = threading.Lock()

    def catalog(self):
        """Momentaufnahme der echten Knoten, einschließlich Typ, Zugriff, Einheit und letztem Wert."""
        with self._catalog_lock:
            return copy.deepcopy(sorted(self._catalog.values(), key=lambda row: row["identifier"]))

    # ------------------------------------------------------------------ Start/Stopp
    def _choose_port(self):
        bind = "127.0.0.1" if self.local_only else "0.0.0.0"
        if port_free(self.port_wanted, bind):
            return self.port_wanted
        owner = port_owner(self.port_wanted)
        if not self.auto_port:
            self.error = (f"Port {self.port_wanted} ist belegt" + (f" (durch {owner})" if owner else "") +
                          ". Anderen Port wählen oder „Freien Port automatisch wählen“ aktivieren.")
            return None
        for p in range(self.port_wanted + 1, min(65536, self.port_wanted + 200)):
            if port_free(p, bind):
                self.info = (f"Port {self.port_wanted} ist belegt" + (f" durch {owner}" if owner else "") +
                             f" – Ximaj-Server läuft auf Port {p}.")
                return p
        self.error = "Kein freier Port gefunden."
        return None

    def start(self):
        if not AVAILABLE:
            self.error = "Paket 'asyncua' fehlt (pip install asyncua)"
            return False
        if self.running:
            return True
        if self.thread and self.thread.is_alive():
            self.error = "Der vorherige Server wird noch beendet. Bitte kurz warten."
            return False
        self.error = self.info = ""
        with self._catalog_lock:
            self._catalog.clear()
        port = self._choose_port()
        if port is None:
            return False
        self.port = port
        self.endpoint = f"opc.tcp://{'localhost' if self.local_only else self.host}:{port}/ximaj/robosim"
        self._stop.clear()
        self.thread = threading.Thread(target=lambda: asyncio.run(self._main()), daemon=True)
        self.thread.start()
        t0 = time.time()
        while not self.running and not self.error and time.time() - t0 < 8:
            time.sleep(0.05)
        if not self.running and not self.error:
            self.error = "Serverstart hat das Zeitlimit überschritten."
            self._stop.set()
        return self.running

    def stop(self):
        self._stop.set()
        if self.thread:
            self.thread.join(timeout=4)
        self.running = False

    def endpoints(self):
        """alle Adressen, unter denen Clients den Server erreichen"""
        urls = [f"opc.tcp://localhost:{self.port}/ximaj/robosim"]
        if not self.local_only:
            urls.append(f"opc.tcp://{self.host}:{self.port}/ximaj/robosim")
            try:
                for ip in sorted({a[4][0] for a in socket.getaddrinfo(self.host, None, socket.AF_INET)}):
                    if not ip.startswith("127."):
                        urls.append(f"opc.tcp://{ip}:{self.port}/ximaj/robosim")
            except Exception:
                pass
        return urls

    # ------------------------------------------------------------------ Server
    async def _main(self):
        sim = self.sim
        try:
            srv = Server()
            await srv.init()
            bind = "127.0.0.1" if self.local_only else "0.0.0.0"
            srv.set_endpoint(f"opc.tcp://{bind}:{self.port}/ximaj/robosim")
            srv.set_server_name("Ximaj RoboSim OPC UA")
            srv.set_security_policy([ua.SecurityPolicyType.NoSecurity])
            try:
                await srv.set_application_uri("urn:ximaj:robosim:server")
            except Exception:
                pass
            idx = self.namespace_index = await srv.register_namespace(NAMESPACE_URI)
            root = await srv.nodes.objects.add_object(ua.NodeId(ROOT_ID, idx), ua.QualifiedName("XimajRoboSim", idx))

            def record(node, cls, val=None, writable=False, unit="", frame="", vt=""):
                identifier = str(node.nodeid.Identifier)
                with self._catalog_lock:
                    self._catalog[identifier] = {"path": identifier, "node_id": node.nodeid.to_string(),
                        "namespace_uri": NAMESPACE_URI, "identifier": identifier, "node_class": cls,
                        "data_type": vt, "access": "lesen/schreiben" if writable else "lesen",
                        "unit": unit, "frame": frame, "value": val}
            record(root, "Object")

            async def obj(parent, name, identifier=None):
                node = await parent.add_object(ua.NodeId(identifier or child_id(parent.nodeid.Identifier, name), idx), ua.QualifiedName(name, idx))
                record(node, "Object")
                return node

            async def method(parent, name, callback, inputs=None):
                node = await parent.add_method(ua.NodeId(child_id(parent.nodeid.Identifier, name), idx),
                                              ua.QualifiedName(name, idx), callback, inputs or [], [])
                record(node, "Method")
                with self._catalog_lock:
                    self._catalog[node.nodeid.Identifier]["access"] = "aufrufen"

            async def write(node, value):
                await node.write_value(value)
                with self._catalog_lock:
                    row = self._catalog.get(node.nodeid.Identifier)
                    if row is not None:
                        row["value"] = value

            async def read(node):
                value = await node.read_value()
                with self._catalog_lock:
                    row = self._catalog.get(node.nodeid.Identifier)
                    if row is not None:
                        row["value"] = value
                return value

            async def remove(node):
                await srv.delete_nodes([node], recursive=True)
                prefix = node.nodeid.Identifier
                with self._catalog_lock:
                    for key in list(self._catalog):
                        if key == prefix or key.startswith(prefix + "/"):
                            del self._catalog[key]

            async def var(parent, name, val, writable=False, desc=None, unit="", frame=""):
                v = await parent.add_variable(ua.NodeId(child_id(parent.nodeid.Identifier, name), idx), ua.QualifiedName(name, idx), val)
                if writable:
                    await v.set_writable()
                record(v, "Variable", val, writable, unit, frame, (await v.read_data_type_as_variant_type()).name)
                if unit or frame:
                    desc = " · ".join(x for x in (desc, f"Einheit: {unit}" if unit else "", f"Bezug: {frame}" if frame else "") if x)
                if desc:
                    try:
                        await v.write_attribute(ua.AttributeIds.Description, ua.DataValue(ua.Variant(ua.LocalizedText(desc))))
                    except Exception:
                        pass
                return v

            def cmd(name, robot=None):
                @uamethod
                def f(parent):
                    self.commands.append((name, None, robot))
                return f

            def cmd_load(robot=None):
                @uamethod
                def f(parent, text):
                    self.commands.append(("load", text, robot))
                return f

            # Simulation
            simo = await obj(root, "Simulation")
            v_sim = {"State": await var(simo, "State", "idle"), "Time": await var(simo, "Time", 0.0),
                     "SpeedFactor": await var(simo, "SpeedFactor", 1.0, True), "RobotCount": await var(simo, "RobotCount", 0)}
            for n, c in (("StartAll", "start_all"), ("StopAll", "stop_all"), ("ResetAll", "reset")):
                await method(simo, n, cmd(c))

            async def robot_nodes(parent, name, robot_name):
                ro = await obj(parent, name)
                axes = await obj(ro, "Axes")
                tcp = await obj(ro, "Tcp")
                world = await obj(ro, "TcpWorld")
                points = await obj(ro, "Points")
                gripper = await obj(ro, "Gripper")
                nodes = {"obj": ro,
                         "State": await var(ro, "State", "idle"), "Line": await var(ro, "Line", 0),
                         "Message": await var(ro, "Message", ""), "Model": await var(ro, "Model", ""),
                         "Override": await var(ro, "Override", 100.0, True), "Collision": await var(ro, "Collision", ""),
                         "CycleTime": await var(ro, "CycleTime", 0.0), "EnergyWh": await var(ro, "EnergyWh", 0.0),
                         "E1": await var(ro, "E1", 0.0, unit="mm"),
                         "Axes": [await var(axes, f"A{i + 1}", 0.0, unit="deg", frame="Roboterachse") for i in range(6)],
                         "JointPosition": await var(axes, "JointPosition", [0.0] * 6, unit="deg", frame="A1–A6"),
                         "Tcp": [await var(tcp, n, 0.0, unit="mm" if n in "XYZ" else "deg", frame="aktuelle BASE") for n in "XYZABC"],
                         "TcpPose": await var(tcp, "Pose", [0.0] * 6, unit="mm, deg", frame="aktuelle BASE; X,Y,Z,A,B,C"),
                         "TcpWorld": [await var(world, n, 0.0, unit="mm" if n in "XYZ" else "deg", frame="Welt") for n in "XYZABC"],
                         "WorldPose": await var(world, "Pose", [0.0] * 6, unit="mm, deg", frame="Welt; X,Y,Z,A,B,C"),
                         "BaseWorld": await var(ro, "BaseWorld", [0.0] * 6, unit="mm, deg", frame="BASE relativ zur Welt"),
                         "Gripper": {"SignalIndex": await var(gripper, "SignalIndex", 0),
                                     "Command": await var(gripper, "Command", False),
                                     "Holding": await var(gripper, "Holding", False),
                                     "Part": await var(gripper, "Part", ""),
                                     "NearestDistance": await var(gripper, "NearestDistance", 0.0, unit="mm", frame="TCP zur Werkstück-Hülle"),
                                     "MappingConflict": await var(gripper, "MappingConflict", "")},
                         "Points": points, "PointNodes": {}, "PointCount": await var(ro, "PointCount", 0), "ovr": 100.0}
                for n, c in (("Start", "start"), ("Stop", "stop"), ("Pause", "pause"), ("Reset", "reset")):
                    await method(ro, n, cmd(c, robot_name))
                await method(ro, "LoadProgram", cmd_load(robot_name), [ua.VariantType.String])
                return nodes

            robots_f = await obj(root, "Robots")
            rnodes = {}
            active = await robot_nodes(root, "Robot", None)          # kompatibel: aktiver Roboter
            for n, c in (("Start", "start"), ("Stop", "stop"), ("Pause", "pause"), ("Reset", "reset")):
                await method(root, n, cmd(c))
            await method(root, "LoadProgram", cmd_load(), [ua.VariantType.String])

            iof = await obj(root, "IO")
            ino = await obj(iof, "In")
            outo = await obj(iof, "Out")
            names = getattr(sim.io, "names", {}) or {}
            v_in = [await var(ino, f"I{i + 1}", False, True, names.get(("in", i + 1))) for i in range(self.n_io)]
            v_out = [await var(outo, f"O{i + 1}", False, True, names.get(("out", i + 1))) for i in range(self.n_io)]
            comp_f = await obj(root, "Components")
            cnodes = {}

            async def sync_components():
                live = {o.name: o for o in list(sim.scene) if not getattr(o, "_runtime_created", False)}
                for name in list(cnodes):
                    if live.get(name) is not cnodes[name][0]:
                        await remove(cnodes.pop(name)[1]["_obj"])
                for o in list(sim.scene):
                    if o.kind not in ("sensor", "conveyor", "conveyor_arc", "spawner", "color_sensor", "lamp") or o.name in cnodes:
                        continue
                    if getattr(o, "_runtime_created", False):
                        continue
                    co = await obj(comp_f, o.name)
                    d = {"_obj": co}
                    if o.kind == "sensor":
                        d["Signal"] = await var(co, "Signal", False)
                    elif o.kind in ("conveyor", "conveyor_arc"):
                        d["Running"] = await var(co, "Running", True)
                        d["Speed"] = await var(co, "Speed", float(o.speed), True)
                    elif o.kind == "spawner":
                        d["Created"] = await var(co, "Created", 0)
                    elif o.kind == "color_sensor":
                        d["Detected"] = await var(co, "Detected", False)
                        d["Color"] = await var(co, "Color", "")
                    elif o.kind == "lamp":
                        d["Color"] = await var(co, "Color", "")
                    d["_speed"] = float(o.speed)
                    cnodes[o.name] = (o, d)

            def sig(n):
                n = int(n or 0)
                return n > 0 and bool(sim.io.get_in(n) or sim.io.get_out(n))

            def pose(value):
                try:
                    result = [float(x) for x in value]
                    if len(result) == 6 and all(math.isfinite(x) for x in result):
                        return result, True
                except (TypeError, ValueError):
                    pass
                return [float("nan")] * 6, False

            async def sync_points(nodes, r):
                existing = nodes["PointNodes"]
                counts, live = {}, {}
                for i, point in enumerate(list(r.waypoints)):
                    name = str(point.get("name", f"P{i + 1}"))
                    counts[name] = counts.get(name, 0) + 1
                    key = (name, counts[name])
                    live[key] = point
                    if key not in existing:
                        identifier = child_id(nodes["Points"].nodeid.Identifier, name)
                        if key[1] > 1:
                            identifier += f"/Duplicate/{key[1]}"
                        po = await obj(nodes["Points"], name if key[1] == 1 else f"{name} [{key[1]}]", identifier)
                        d = {"obj": po, "Name": await var(po, "Name", name), "Valid": await var(po, "Valid", False),
                             "S": await var(po, "S", 0), "T": await var(po, "T", 0),
                             "Pose": await var(po, "Pose", [0.0] * 6, unit="mm, deg", frame="BASE beim Einlernen; X,Y,Z,A,B,C"),
                             "Coords": [await var(po, n, 0.0, unit="mm" if n in "XYZ" else "deg", frame="BASE beim Einlernen") for n in "XYZABC"],
                             "WorldKnown": await var(po, "WorldKnown", False),
                             "WorldPose": await var(po, "WorldPose", [0.0] * 6, unit="mm, deg", frame="Welt beim Einlernen; nur gültig wenn WorldKnown"),
                             "E1Known": await var(po, "E1Known", False), "E1": await var(po, "E1", 0.0, unit="mm")}
                        existing[key] = d
                for key in set(existing) - set(live):
                    await remove(existing.pop(key)["obj"])
                for key, point in live.items():
                    d = existing[key]
                    coords, valid = pose(point.get("pos"))
                    base, base_valid = pose(point.get("base_world"))
                    known = valid and base_valid
                    world = [float(x) for x in mat_to_pose(pose_to_mat(*base) @ pose_to_mat(*coords))] if known else [float("nan")] * 6
                    for field, value in (("Name", key[0]), ("Valid", valid), ("Pose", coords), ("WorldKnown", known),
                                         ("WorldPose", world), ("S", int(point.get("S", 0))), ("T", int(point.get("T", 0))),
                                         ("E1Known", "e1" in point), ("E1", float(point.get("e1", float("nan"))))):
                        await write(d[field], value)
                    for node, value in zip(d["Coords"], coords):
                        await write(node, value)
                await write(nodes["PointCount"], len(live))

            async def write_robot(nodes, r):
                await write(nodes["State"], str(r.state))
                await write(nodes["Line"], int(r.cur_line or 0))
                await write(nodes["Message"], str(getattr(r, "message", None) or getattr(sim, "message", "") or ""))
                await write(nodes["Model"], r.model_key)
                await write(nodes["Collision"], r.collision or "")
                await write(nodes["CycleTime"], float(r.cycle_times[-1] if r.cycle_times else 0.0))
                await write(nodes["EnergyWh"], float(getattr(r, "energy_wh", 0.0)))
                await write(nodes["E1"], float(getattr(r, "e1", 0.0) or 0.0))
                joints = [float(x) for x in r.q.copy()]
                pos = [float(x) for x in mat_to_pose(r.tcp_in_base(joints))]
                world = [float(x) for x in mat_to_pose(r.tcp_world(joints))]
                base = [float(x) for x in mat_to_pose(r.base_world())]
                await write(nodes["JointPosition"], joints)
                await write(nodes["TcpPose"], pos)
                await write(nodes["WorldPose"], world)
                await write(nodes["BaseWorld"], base)
                for i in range(6):
                    await write(nodes["Axes"][i], joints[i])
                    await write(nodes["Tcp"][i], pos[i])
                    await write(nodes["TcpWorld"][i], world[i])
                await sync_points(nodes, r)
                grip = r.gripper_info()
                for field, value in (("SignalIndex", grip["output"]), ("Command", grip["command"]),
                                     ("Holding", grip["holding"]), ("Part", grip["part"]),
                                     ("NearestDistance", grip["distance"] if math.isfinite(grip["distance"]) else float("nan")),
                                     ("MappingConflict", ", ".join(grip["conflicts"]))):
                    await write(nodes["Gripper"][field], value)
                o = float(await read(nodes["Override"]))       # Override von aussen (gilt fuer die Zelle)
                if o != nodes["ovr"]:
                    nodes["ovr"] = o
                    sim.override = max(0.0, min(1.0, o / 100.0))
                elif abs(sim.override * 100.0 - nodes["ovr"]) > 1e-6:
                    nodes["ovr"] = sim.override * 100.0
                    await write(nodes["Override"], nodes["ovr"])

            # Erst nach Aufbau und Befüllung als bereit melden: sofortiges Browsen ist vollständig.
            for r in list(sim.robots):
                rnodes[r.name] = await robot_nodes(robots_f, r.name, r.name)
                await write_robot(rnodes[r.name], r)
            await write_robot(active, sim.active)
            await sync_components()

            async with srv:
                self.running = True
                last_out = [False] * self.n_io
                last_in = [False] * self.n_io
                last_spd = 1.0
                tick = 0
                while not self._stop.is_set():
                    try:
                        tick += 1
                        live_robots = {r.name for r in list(sim.robots)}
                        for name in set(rnodes) - live_robots:
                            await remove(rnodes.pop(name)["obj"])
                        # neue Roboter/Komponenten zur Laufzeit ergaenzen
                        for r in list(sim.robots):
                            if r.name not in rnodes:
                                rnodes[r.name] = await robot_nodes(robots_f, r.name, r.name)
                        if tick % 20 == 1:
                            await sync_components()
                        for r in list(sim.robots):
                            await write_robot(rnodes[r.name], r)
                        await write_robot(active, sim.active)
                        busy = any(r.state in ("running", "wait") for r in sim.robots)
                        await write(v_sim["State"], "running" if busy else "idle")
                        await write(v_sim["Time"], float(getattr(sim, "t", 0.0)))
                        await write(v_sim["RobotCount"], len(sim.robots))
                        sp = float(await read(v_sim["SpeedFactor"]))
                        if sp != last_spd and sp > 0:
                            sim.speed_factor = sp
                            last_spd = sp
                        elif sim.speed_factor != last_spd:
                            last_spd = sim.speed_factor
                            await write(v_sim["SpeedFactor"], float(last_spd))
                        for i in range(self.n_io):
                            cur_in = await read(v_in[i])
                            if cur_in != last_in[i]:            # nur Aenderungen von aussen uebernehmen
                                sim.io.set_in(i + 1, bool(cur_in))
                                last_in[i] = bool(cur_in)
                            elif sim.io.get_in(i + 1) != last_in[i]:
                                last_in[i] = sim.io.get_in(i + 1)
                                await write(v_in[i], last_in[i])
                            if sim.io.get_out(i + 1) != last_out[i]:
                                last_out[i] = sim.io.get_out(i + 1)
                                await write(v_out[i], last_out[i])
                            else:
                                ext = await read(v_out[i])
                                if ext != last_out[i]:          # SPS setzt Ausgang
                                    sim.io.set_out(i + 1, bool(ext))
                                    last_out[i] = bool(ext)
                        for name, (o, d) in list(cnodes.items()):
                            if "Signal" in d:
                                await write(d["Signal"], sig(o.io))
                            if "Running" in d:
                                run = not getattr(o, "stopped", False) and (not o.io or sim._driven(o, o.io))
                                await write(d["Running"], bool(run))
                                spd = float(await read(d["Speed"]))
                                if spd != d["_speed"]:
                                    o.speed = d["_speed"] = spd
                                elif o.speed != d["_speed"]:
                                    d["_speed"] = float(o.speed)
                                    await write(d["Speed"], d["_speed"])
                            if "Created" in d:
                                await write(d["Created"], int(getattr(o, "spawned", 0)))
                            if "Detected" in d:
                                await write(d["Detected"], sig(getattr(o, "detected", 0)))
                                await write(d["Color"], next((k for k, n in (getattr(o, "color_outs", None) or {}).items() if sig(n)), ""))
                            if o.kind == "lamp":
                                lit = getattr(o, "lit_color", None)
                                await write(d["Color"], "" if lit is None else str(lit))
                        try:
                            self.sessions = len(srv.iserver.subscription_service.subscriptions) if False else \
                                len(getattr(srv.bserver, "clients", []) or [])
                        except Exception:
                            pass
                        self.error = ""
                    except Exception as e:
                        self.error = str(e)
                    await asyncio.sleep(0.05)
        except Exception as e:
            self.error = f"{type(e).__name__}: {e}"
        finally:
            self.running = False
