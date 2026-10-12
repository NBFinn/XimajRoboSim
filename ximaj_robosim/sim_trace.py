"""Simulation-time recorder with bounded online history and CSV export."""
import csv
from collections import deque
import numpy as np


class Recorder:
    def __init__(self, sim, max_seconds=600):
        if max_seconds <= 0:
            raise ValueError('Aufzeichnungsdauer muss positiv sein')
        self.sim, self.max_seconds = sim, float(max_seconds)
        self.active = False
        self.online = True
        self.clear()

    def start(self):
        self.active = True
        self.sim.recorder = self
        self._previous.clear()
        self._bits.clear()
        self._starts.clear()

    def stop(self):
        self.active = False

    def clear(self):
        self.samples = deque()
        self._previous = {}
        self._bits = {}
        self._starts = {}
        self._states = {}
        self._cycles = {}
        self._max_speeds = {}
        self._cycle_counts = {}

    def sample(self, sim):
        if not self.active:
            return
        t = float(sim.t)
        if self.samples and t < self.samples[-1]['t']:
            self.clear()  # A reset begins a new simulation-time trace.
        if self.samples and t == self.samples[-1]['t']:
            return
        row = {'t': t, 'robots': {}}
        for r in sim.robots:
            tcp = r.tcp_world()[:3, 3].copy()
            prev = self._previous.get(r.name)
            speed = float(np.linalg.norm(tcp-prev[1])/(t-prev[0])) if prev and t > prev[0] else 0.
            self._previous[r.name] = (t, tcp)
            changes = {}
            for key, bits in [('inputs', r.io.inp), ('outputs', r.io.out)]:
                old = self._bits.get((r.name, key), [False]*len(bits))
                changes[key] = {i: bool(value) for i, value in enumerate(bits) if value != old[i]}
                self._bits[r.name, key] = list(bits)
            row['robots'][r.name] = dict(q=np.asarray(r.q).tolist(), tcp=tcp.tolist(), speed=speed, **changes)
            self._max_speeds[r.name] = max(speed, self._max_speeds.get(r.name, 0.))
            running = r.state in ('running', 'wait', 'paused', 'stopping')
            previous = self._states.get(r.name)
            if running and previous not in ('running', 'wait', 'paused', 'stopping'):
                self._starts[r.name] = t-r.run_t
            if r.state == 'idle' and previous in ('running', 'wait') and r.name in self._starts:
                self._cycles.setdefault(r.name, []).append(t-self._starts.pop(r.name))
            count = self._cycle_counts.get(r.name, 0)
            if len(r.cycle_times) > count:
                self._cycles.setdefault(r.name, []).extend(r.cycle_times[count:])
            self._cycle_counts[r.name] = len(r.cycle_times)
            self._states[r.name] = r.state
        self.samples.append(row)
        if self.online:
            while self.samples and self.samples[0]['t'] < t-self.max_seconds:
                self.samples.popleft()

    def series(self, robot_name, key):
        aliases = {'tcp_speed': 'speed', 'tcp_xyz': 'tcp'}
        key = aliases.get(key, key)
        times, values = [], []
        for row in self.samples:
            if robot_name not in row['robots']:
                continue
            data = row['robots'][robot_name]
            if key not in data:
                raise KeyError(key)
            times.append(row['t'])
            values.append(data[key])
        width = {'q': 6, 'tcp': 3}.get(key)
        array = np.asarray(values, dtype=object if key in ('inputs', 'outputs') else float)
        if width and not values:
            array = array.reshape(0, width)
        return np.asarray(times, float), array

    def to_csv(self, path):
        with open(path, 'w', newline='', encoding='utf-8') as stream:
            writer = csv.writer(stream)
            writer.writerow(['t', 'robot', *[f'q{i+1}' for i in range(6)], 'tcp_x', 'tcp_y', 'tcp_z', 'speed', 'inputs', 'outputs'])
            for row in self.samples:
                for name, data in row['robots'].items():
                    fmt = lambda bits: ';'.join(f'{i}={int(v)}' for i, v in bits.items())
                    writer.writerow([row['t'], name, *data['q'], *data['tcp'], data['speed'], fmt(data['inputs']), fmt(data['outputs'])])

    def stats(self):
        return {'cycle_times': {k: list(v) for k, v in self._cycles.items()}, 'max_speeds': dict(self._max_speeds)}
