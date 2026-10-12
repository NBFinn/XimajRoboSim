"""Opt-in VC compatibility runtime for trusted component scripts.

The import allowlist is a compatibility boundary, not a security sandbox.
Scripts execute in-process and must come from trusted projects.
"""
import builtins
import copy
import importlib
import re
from types import ModuleType, SimpleNamespace


class Unsupported:
    def __init__(self, api):
        self.api = api

    def __getattr__(self, name):
        raise NotImplementedError(self.api + '.' + name)


class Color:
    def __init__(self, r=0, g=0, b=0, a=1):
        self.R, self.G, self.B, self.A = r, g, b, a

    def hex(self):
        return '#%02x%02x%02x' % tuple(round(max(0, min(1, x)) * 255) for x in (self.R, self.G, self.B))


class Property:
    def __init__(self, component, name, value):
        self.component, self.Name, self._value = component, name, value
        self.OnChanged = None

    @property
    def Value(self):
        return self._value

    @Value.setter
    def Value(self, value):
        if value == self._value:
            return
        self._value = value
        if self.OnChanged:
            if not self.component.host.callback(self.component, self.OnChanged, self):
                self.OnChanged = None


class SignalObj:
    def __init__(self, component, name, kind='bool', value=False, AutomaticReset=True):
        self.component, self.Name, self.kind = component, name, kind
        self.AutomaticReset = AutomaticReset
        self._value = self.convert(value)

    def convert(self, value):
        return {'bool': bool, 'int': int, 'real': float, 'string': str}[self.kind](value)

    @property
    def Value(self):
        return self._value

    @Value.setter
    def Value(self, value):
        self.signal(value)

    def signal(self, value):
        self.component.host.change(self, self.convert(value))


class Component:
    def __init__(self, host, obj, data):
        self.host, self.obj, self.data = host, obj, copy.deepcopy(data)
        self.signals = {name: SignalObj(self, name, **spec) for name, spec in data.get('signals', {}).items()}
        props = dict(data.get('properties', {}))
        size = getattr(obj, 'size', (0, 0, 0))
        for name, value in zip(('Length', 'Width', 'Height'), size):
            props.setdefault(name, value)
        self.properties = {name: Property(self, name, value) for name, value in props.items()}
        self.scripts = []
        self._loaded = False
        self.MaterialInheritance = None
        self._material = None
        self.initial_color = getattr(obj, 'color', None)
        self.RootFeature = Unsupported('RootFeature')

    Name = property(lambda self: getattr(self.obj, 'vc_component', self.obj.name))
    WorldPositionMatrix = property(lambda self: SimpleNamespace(P=SimpleNamespace(
        **dict(zip(('X', 'Y', 'Z'), getattr(self.obj, 'pos', getattr(self.obj, 'root', (0, 0, 0)))[:3])))))

    def findBehavior(self, name):
        return self.signals.get(name)

    findBehaviour = getBehaviour = findBehavior

    def getProperty(self, name):
        return self.properties.get(name)

    def __getattr__(self, name):
        props = self.__dict__.get('properties', {})
        if name in props:
            return props[name].Value
        raise NotImplementedError('Component.' + name)

    @property
    def NodeMaterial(self):
        return self._material

    @NodeMaterial.setter
    def NodeMaterial(self, material):
        self._material = material
        if self.MaterialInheritance == 'FORCE_INHERIT' and hasattr(self.obj, 'color'):
            for obj in self.host.sim.scene:
                if getattr(obj, 'vc_component', obj.name) == self.Name:
                    obj.color = material.Diffuse.hex()
                    obj.alpha = material.Opacity


class ScriptHost:
    ALLOWED = {'math', 'random', 'time', 're', 'json', 'collections', 'itertools', 'functools'}

    def __init__(self, sim):
        self.sim = sim
        self.components = {}
        self.materials = {}
        self.running = False
        self._active = set()
        self._depth = 0
        self._reported = set()
        self._last_update = -float('inf')
        self.sync()

    @property
    def Components(self):
        return list(self.components.values())

    def findMaterial(self, name):
        return self.materials.get(name)

    def createMaterial(self, name):
        mat = SimpleNamespace(Name=name, Ambient=Color(), Diffuse=Color(), Opacity=1.)
        self.materials[name] = mat
        return mat

    def render(self):
        pass

    def warning(self, component, api):
        key = (component.Name, api)
        if key not in self._reported:
            self._reported.add(key)
            self.sim.say(f'Skript {component.Name}: {api} wird noch nicht unterstuetzt')

    def callback(self, component, callback, *args):
        try:
            callback(*args)
            return True
        except (NotImplementedError, AttributeError) as exc:
            self.warning(component, str(exc))
        except Exception as exc:
            self.sim.say(f'Skriptfehler {component.Name}: {type(exc).__name__}: {exc}')
        return False

    def modules(self, component):
        core = ModuleType('vcCore')
        core.getComponent = lambda: component
        core.getWorld = core.getApplication = lambda: self
        core.getSimulation = lambda: Unsupported('Simulation')
        core.vcColor = Color
        core.vcMaterialInheritance = SimpleNamespace(FORCE_INHERIT='FORCE_INHERIT')
        core.VC_MATERIAL_FORCE_INHERIT = 'FORCE_INHERIT'
        def unsupported_delay(*args):
            raise NotImplementedError('delay/OnRun')
        core.delay = core.triggerCondition = unsupported_delay
        script = ModuleType('vcScript')
        script.__dict__.update({k: v for k, v in core.__dict__.items() if not k.startswith('__')})
        for name in ('VC_GEOMETRY', 'VC_TRIANGLESET', 'VC_BUTTON', 'VC_STRING'):
            setattr(script, name, name)
        vector = ModuleType('vcVector')
        vector.new = lambda x=0, y=0, z=0: SimpleNamespace(X=x, Y=y, Z=z)
        matrix = ModuleType('vcMatrix')
        matrix.new = lambda *args: Unsupported('vcMatrix')
        random = ModuleType('random')
        for name in ('random', 'choice', 'choices', 'randint', 'randrange', 'uniform', 'shuffle', 'sample', 'seed', 'getrandbits'):
            setattr(random, name, getattr(self.sim.rng, name))
        return {'vcCore': core, 'vcScript': script, 'vcVector': vector, 'vcMatrix': matrix, 'random': random}

    def load(self, component):
        component.scripts.clear()
        modules = self.modules(component)
        def restricted_import(name, globals=None, locals=None, fromlist=(), level=0):
            if level or (name not in modules and name not in self.ALLOWED):
                raise ImportError(f'Import {name} ist nicht erlaubt')
            return modules[name] if name in modules else importlib.import_module(name)
        safe = {k: v for k, v in vars(builtins).items() if k not in
                {'open', 'input', 'eval', 'exec', 'compile', 'breakpoint', '__import__'}}
        safe['__import__'] = restricted_import
        safe['print'] = lambda *args, sep=' ', end='\n': self.sim.say(component.Name + ': ' + sep.join(map(str, args)).rstrip())
        for source in component.data.get('scripts', []):
            namespace = {'__builtins__': safe, '__name__': '__vc_component__'}
            try:
                exec(source, namespace)
            except ImportError as exc:
                self.warning(component, str(exc))
                continue
            except (NotImplementedError, AttributeError) as exc:
                self.warning(component, str(exc))
                continue
            except Exception as exc:
                self.sim.say(f'Skriptfehler {component.Name}: {type(exc).__name__}: {exc}')
                continue
            component.scripts.append(namespace)
            if callable(namespace.get('OnRun')):
                self.warning(component, 'OnRun/Coroutinen')
        self.dispatch(component, 'OnFinalize')

    def dispatch(self, component, handler, *args):
        for namespace in component.scripts:
            callback = namespace.get(handler)
            if callable(callback) and not self.callback(component, callback, *args):
                namespace.pop(handler, None)

    def sync(self):
        objects = self.sim.scene + self.sim.robots
        live = {getattr(o, 'vc_component', o.name) for o in objects}
        for name in list(self.components):
            if name not in live:
                del self.components[name]
        for obj in objects:
            name = getattr(obj, 'vc_component', obj.name)
            if name in self.components and self.components[name].obj in objects:
                continue
            data = getattr(obj, 'vc_data', {})
            component = Component(self, obj, data)
            self.components[name] = component
        # Register all wrappers before executing scripts that inspect the world.
        for component in self.Components:
            if not component._loaded:
                component._loaded = True
                self.load(component)
                for obj in self.sim.scene:
                    if getattr(obj, 'vc_component', obj.name) == component.Name:
                        obj.scripted = bool(component.data.get('scripts'))
                if self.running:
                    self.dispatch(component, 'OnStart')

    def start(self):
        if self.running:
            return
        self.running = True
        for component in self.Components:
            self.dispatch(component, 'OnStart')

    def reset(self):
        self.running = False
        self._last_update = -float('inf')
        self.materials.clear()
        for component in self.Components:
            if component.initial_color is not None:
                for obj in self.sim.scene:
                    if getattr(obj, 'vc_component', obj.name) == component.Name:
                        obj.color = component.initial_color
        self.components.clear()
        self.sync()
        for component in self.Components:
            self.dispatch(component, 'OnReset')

    def change(self, signal, value):
        key = (signal.component.Name, signal.Name)
        if value == signal._value or key in self._active:
            return
        if self._depth >= 32:
            self.warning(signal.component, 'Signal-Rekursion (max. 32)')
            return
        signal._value = value
        self._active.add(key)
        self._depth += 1
        try:
            self.dispatch(signal.component, 'OnSignal', signal)
            # Route immediately so handlers observe the same signal event.
            for link in self.sim.links:
                if tuple(link['src']) == key:
                    self.deliver(tuple(link['dst']), value)
        finally:
            self._depth -= 1
            self._active.remove(key)

    def source(self, endpoint):
        component = self.components.get(endpoint[0])
        signal = component.signals.get(endpoint[1]) if component else None
        if signal and not re.fullmatch(r'(?:Inputs|Outputs)_Port_\d+', endpoint[1]) and (
                getattr(component.obj, 'scripted', False) or getattr(component.obj, 'kind', None) not in ('sensor', 'color_sensor')):
            return signal.Value
        return self.sim._source_signal(endpoint, native=True)

    def deliver(self, endpoint, value):
        component = self.components.get(endpoint[0])
        signal = component.signals.get(endpoint[1]) if component else None
        if signal:
            signal.signal(value)
        port = re.fullmatch(r'Inputs_Port_(\d+)', endpoint[1])
        if port:
            robot = next((r for r in self.sim.robots if r.name == endpoint[0]), None)
            if robot:
                robot.io.set_in(int(port[1]), bool(value))

    def route(self):
        for component in self.Components:
            if getattr(component.obj, 'kind', None) == 'sensor':
                signal = component.signals.get('SensorBooleanSignal')
                if signal:
                    signal.signal(self.sim.io.get_in(component.obj.io))
        values = {}
        for link in self.sim.links:
            endpoint = tuple(link['dst'])
            value = self.source(link['src'])
            if endpoint in values and isinstance(value, bool):
                value = values[endpoint] or value
            values[endpoint] = value
        for endpoint, value in values.items():
            self.deliver(endpoint, value)

    def update(self):
        if self.sim.t - self._last_update >= .05 - 1e-9:
            self._last_update = self.sim.t
            self.sync()
            for component in self.Components:
                self.dispatch(component, 'OnSimulationUpdate', self.sim.t)

    def clone(self, part, template):
        part.vc_data = copy.deepcopy(template)
        part.scripted = bool(template.get('scripts'))
        self.sync()

    def remove(self, obj):
        self.components.pop(getattr(obj, 'vc_component', obj.name), None)
