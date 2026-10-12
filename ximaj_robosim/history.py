"""Qt-free project history and bounded, atomic crash backups."""
from functools import wraps
import inspect
import json
import os
from pathlib import Path
import time


class History:
    def __init__(self, sim, limit=50):
        self.sim = sim
        self.limit = max(1, int(limit))
        self._states = []
        self._index = -1
        self.snapshot()

    @property
    def busy(self):
        return any(r.state in ('running', 'wait', 'stopping', 'paused')
                   for r in self.sim.robots)

    @property
    def current(self):
        return self._states[self._index] if self._index >= 0 else None

    @property
    def can_undo(self):
        return not self.busy and self._index > 0

    @property
    def can_redo(self):
        return not self.busy and self._index < len(self._states) - 1

    def snapshot(self):
        if self.busy:
            return False
        state = json.dumps(self.sim.to_dict(), sort_keys=True, ensure_ascii=False)
        if state == self.current:
            return False
        del self._states[self._index + 1:]
        self._states.append(state)
        # Keep the initial state plus at most limit undo steps.
        self._states = self._states[-(self.limit + 1):]
        self._index = len(self._states) - 1
        return True

    def _restore(self, index):
        self.sim.reset_world()
        self.sim.from_dict(json.loads(self._states[index]))
        self._index = index
        return True

    def undo(self):
        return self._restore(self._index - 1) if self.can_undo else False

    def redo(self):
        return self._restore(self._index + 1) if self.can_redo else False


def tracked(fn):
    """Record one completed user operation, including nested editing calls."""
    parameters = list(inspect.signature(fn).parameters.values())[1:]
    positional = sum(p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD) for p in parameters)
    variadic = any(p.kind == p.VAR_POSITIONAL for p in parameters)

    @wraps(fn)
    def wrapped(self, *args, **kwargs):
        # Qt normally drops surplus signal arguments for fixed-arity slots.
        # The variadic wrapper must preserve that behavior (clicked(bool), etc.).
        if not variadic:
            args = args[:positional]
        win = getattr(self, 'win', self)
        win._change_depth = getattr(win, '_change_depth', 0) + 1
        try:
            return fn(self, *args, **kwargs)
        finally:
            win._change_depth -= 1
            if not win._change_depth:
                win.mark_changed()
    return wrapped


class Autosave:
    def __init__(self):
        self.directory = Path(os.environ.get('APPDATA', Path.home())) / 'XimajRoboSim' / 'autosave'

    def files(self):
        return sorted(self.directory.glob('*.json'), key=lambda p: p.stat().st_mtime_ns)

    def write(self, snapshot, project_path=None):
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f'{time.time_ns()}.json'
        temporary = path.with_suffix('.tmp')
        payload = {'project_path': str(project_path) if project_path else None,
                   'project': json.loads(snapshot)}
        try:
            temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf8')
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        for old in self.files()[:-5]:
            old.unlink()
        return path

    def candidates(self):
        result = []
        for path in reversed(self.files()):
            try:
                payload = json.loads(path.read_text(encoding='utf8'))
                project = payload.get('project_path')
                if not isinstance(payload.get('project'), dict):
                    continue
                if not project or not Path(project).exists() or path.stat().st_mtime_ns > Path(project).stat().st_mtime_ns:
                    result.append((path, payload))
            except (OSError, ValueError, TypeError):
                continue
        return result

    def clear(self, project_path=None):
        for path in self.files():
            try:
                payload = json.loads(path.read_text(encoding='utf8'))
                if payload.get('project_path') == (str(project_path) if project_path else None):
                    path.unlink()
            except (OSError, ValueError, TypeError):
                continue
