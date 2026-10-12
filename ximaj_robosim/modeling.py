"""Small parametric modeling workspace: editable primitives stored in the project."""
import math
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QFormLayout, QComboBox, QLineEdit, QDoubleSpinBox, QPushButton, QColorDialog, QLabel
from sim import SceneObj

def primitive(kind, name, size, pose, color):
    if kind not in ('box', 'cylinder'):
        raise ValueError('Unbekannter Grundkörper')
    if len(size) != 3 or len(pose) != 6 or not all(math.isfinite(float(v)) for v in (*size, *pose)) or any(v <= 0 for v in size):
        raise ValueError('Maße müssen positiv und Werte endlich sein.')
    size = list(size)
    if kind == 'cylinder':
        size[1] = size[0]
    return SceneObj(name.strip() or 'Eigenes Objekt', kind, pose[:3], pose[3:], size, color, True, False)

def panel(window):
    w = QWidget()
    layout = QVBoxLayout(w)
    help_ = QLabel('Eigene Grundkörper erstellen. Maße und Positionen in mm, Winkel in Grad.\nWeitere Änderungen anschließend im Tab Szene.')
    help_.setWordWrap(True)
    layout.addWidget(help_)
    form = QFormLayout()
    name = QLineEdit('Eigenes Objekt')
    kind = QComboBox(); kind.addItems(['Quader', 'Zylinder'])
    form.addRow('Name', name); form.addRow('Grundkörper', kind)
    fields = []
    for label, value, lo, hi in [('X / Durchmesser', 300, .1, 100000), ('Y', 300, .1, 100000), ('Höhe Z', 300, .1, 100000),
                                ('Position X', 700, -100000, 100000), ('Position Y', 0, -100000, 100000), ('Position Z', 150, -100000, 100000),
                                ('Winkel A', 0, -360, 360), ('Winkel B', 0, -360, 360), ('Winkel C', 0, -360, 360)]:
        field = QDoubleSpinBox(); field.setRange(lo, hi); field.setDecimals(2); field.setValue(value)
        form.addRow(label, field); fields.append(field)
    kind.currentIndexChanged.connect(lambda i: fields[1].setEnabled(i == 0))
    layout.addLayout(form)
    state = {'color': '#8a9bb8'}
    color = QPushButton('Farbe wählen')
    def choose_color():
        value = QColorDialog.getColor(parent=window)
        if value.isValid(): state['color'] = value.name()
    color.clicked.connect(choose_color); layout.addWidget(color)
    create = QPushButton('Objekt erstellen')
    create.setObjectName('primary')
    def insert():
        values = [field.value() for field in fields]
        obj = primitive('box' if kind.currentIndex() == 0 else 'cylinder', name.text(), values[:3], values[3:], state['color'])
        window.sim.scene.append(obj)
        window.refresh_scene_list()
        window.obj_list.setCurrentRow(len(window.sim.scene) - 1)
        window.log_msg(f'Modelliert: {obj.name}')
    create.clicked.connect(insert); layout.addWidget(create)
    layout.addStretch(1)
    # Accessible handles for automated UI regression checks.
    w.model_name, w.model_kind, w.model_fields, w.model_create = name, kind, fields, create
    return w
