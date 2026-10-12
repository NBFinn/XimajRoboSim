"""OPC UA: eigener Server (auch bei belegtem Port), mehrere Roboter, Komponenten, Client-Kopplung."""
import sys, os, time, asyncio, socket
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'ximaj_robosim'))
from sim import Simulation, SceneObj
from opcua_srv import OpcUaService, port_free
from opcua_client import ClientLink
from asyncua import Client

ok = []


def check(name, cond, info=""):
    ok.append(bool(cond))
    print(("OK    " if cond else "FEHLER") + f" {name}" + (f"  ({info})" if info else ""))


# Port absichtlich belegen (wie KukaOpcUa_Simulation auf 4840)
blocker = socket.socket()
blocker.bind(("0.0.0.0", 48410))
blocker.listen(1)

sim = Simulation()
sim.add_robot(None, (2000, 0, 0, 0, 0, 0), "Zweiter")
sim.scene.append(SceneObj("Band A", "conveyor", [500, 0, 0], [0, 0, 0], [2000, 500, 800], "#333333", True, False))
sim.scene.append(SceneObj("LS1", "sensor", [500, 0, 850], [0, 0, 0], [40, 300, 150], "#22d3c5", False, False))
sim.scene[-1].io = 7
srv = OpcUaService(sim, 48410)
started = srv.start()
check("Server startet trotz belegtem Wunschport", started, srv.error)
check("Ausweichport gewählt und gemeldet", srv.port != 48410 and "belegt" in srv.info, f"Port {srv.port}: {srv.info}")
check("Endpunkte mit PC-Name", any(socket.gethostname() in u for u in srv.endpoints()))
sim.io.set_out(3, True)
sim.io.set_in(7, True)
url = f"opc.tcp://127.0.0.1:{srv.port}/ximaj/robosim"


async def client():
    async with Client(url) as c:
        idx = await c.get_namespace_index("urn:ximaj:robosim")
        root = await c.nodes.objects.get_child([f"{idx}:XimajRoboSim"])
        g = lambda *p: root.get_child([f"{idx}:{x}" for x in p])
        await asyncio.sleep(0.4)
        check("Kompatibel: Robot/Axes/A2", abs(await (await g("Robot", "Axes", "A2")).read_value() - float(sim.q[1])) < 1e-6)
        check("Roboter 1 unter Robots", (await (await g("Robots", sim.robots[0].name, "State")).read_value()) == "idle")
        check("Roboter 2 unter Robots", (await (await g("Robots", "Zweiter", "Model")).read_value()) == sim.robots[1].model_key)
        check("Ausgang O3 lesbar", await (await g("IO", "Out", "O3")).read_value() is True)
        await (await g("IO", "In", "I5")).write_value(True)
        await (await g("IO", "In", "I100")).write_value(True)
        await asyncio.sleep(0.4)
        check("Eingang I5 von außen gesetzt", sim.io.get_in(5))
        check("128 E/A verfügbar (I100)", sim.io.get_in(100))
        check("Komponente: Sensor LS1 meldet Signal", await (await g("Components", "LS1", "Signal")).read_value() is True)
        await (await g("Components", "Band A", "Speed")).write_value(321.0)
        await (await g("Simulation", "SpeedFactor")).write_value(2.0)
        await asyncio.sleep(0.4)
        band = next(o for o in sim.scene if o.name == "Band A")
        check("Komponente: Bandgeschwindigkeit schreibbar", abs(band.speed - 321.0) < 1e-6)
        check("Simulation: SpeedFactor schreibbar", sim.speed_factor == 2.0)
        await (await g("Robots", "Zweiter")).call_method(f"{idx}:Start")
        await root.call_method(f"{idx}:Start")
        await asyncio.sleep(0.3)
        check("Methoden: Start je Roboter und aktiver Roboter", ("start", None, "Zweiter") in srv.commands and ("start", None, None) in srv.commands)

asyncio.run(client())

# Client-Kopplung: Ximaj (Client) <-> zweiter Ximaj-Server als „fremde SPS“
plc = Simulation()
plc_srv = OpcUaService(plc, 48450)
check("Zweiter Server (simulierte SPS)", plc_srv.start(), plc_srv.error)
link = ClientLink(sim, f"opc.tcp://127.0.0.1:{plc_srv.port}/ximaj/robosim", "SPS")
rows = link.browse()
nid = lambda path: next(n for p, n, t, v in rows if p.endswith(path))
check("Client: Variablen durchsucht", len(rows) > 100, f"{len(rows)} Variablen")
link.mappings = [{"node": nid("IO/Out/O9"), "dir": "read", "target": "IN:20"},
                 {"node": nid("IO/In/I11"), "dir": "write", "target": "OUT:12"},
                 {"node": nid("Robot/Override"), "dir": "write", "target": "AXIS:Zweiter:1"}]
check("Client: verbunden", link.connect(), link.error)
plc.io.set_out(9, True)
sim.io.set_out(12, True)
sim.robots[1].q[0] = 33.0
time.sleep(1.2)
check("Client lesen: SPS-Ausgang → $IN[20]", sim.io.get_in(20))
check("Client schreiben: $OUT[12] → SPS-Eingang", plc.io.get_in(11))
check("Client schreiben: Achse A1 → Zahlenknoten", abs(link.values.get(nid("Robot/Override"), 0) - 33.0) < 1e-6)
check("Client: keine Zuordnungsfehler", not any(m.get("error") for m in link.mappings), str([m.get("error") for m in link.mappings]))
link.disconnect()
plc_srv.stop()
srv.stop()
blocker.close()
check("Port nach Stopp wieder frei", port_free(srv.port))
print(f"\n{sum(ok)}/{len(ok)} Prüfungen bestanden")
print("OK" if all(ok) else "FEHLER")
