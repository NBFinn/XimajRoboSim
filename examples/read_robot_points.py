"""Echte RoboSim-Knoten lesen, ohne Steuerbefehle zu senden."""
import argparse
import asyncio
from urllib.parse import quote
from asyncua import Client, ua


async def read(endpoint, robot):
    async with Client(endpoint) as client:
        ns = await client.get_namespace_index('urn:ximaj:robosim')
        prefix = 'XimajRoboSim/Robots/' + quote(robot, safe='')
        def node(suffix):
            return client.get_node(ua.NodeId(prefix + '/' + suffix, ns))
        print('Achsen [deg]:', await node('Axes/JointPosition').read_value())
        print('TCP BASE [mm, deg]:', await node('Tcp/Pose').read_value())
        print('TCP Welt [mm, deg]:', await node('TcpWorld/Pose').read_value())
        for point in await node('Points').get_children():
            name = (await point.read_browse_name()).Name
            children = {(await child.read_browse_name()).Name: child for child in await point.get_children()}
            print(name, 'NodeId:', point.nodeid.to_string(), 'Pose:', await children['Pose'].read_value(),
                  'Weltbezug bekannt:', await children['WorldKnown'].read_value())


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--endpoint', required=True)
    p.add_argument('--robot', default='Roboter 1')
    args = p.parse_args()
    asyncio.run(read(args.endpoint, args.robot))
