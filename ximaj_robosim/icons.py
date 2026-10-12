"""Eigener Symbolsatz der Ximaj RoboSim (Linien-Icons, 24x24, selbst gezeichnet).

Jedes Symbol ist ein kleines SVG-Fragment. Farbe A = Linienfarbe, Farbe B = Akzent (Ximaj-Blau).
"""
from functools import lru_cache
from PyQt6.QtCore import QByteArray, Qt, QSize
from PyQt6.QtGui import QIcon, QPixmap, QPainter
from PyQt6.QtSvg import QSvgRenderer

import theme

L = 'fill="none" stroke="{a}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"'
X = 'fill="none" stroke="{b}" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"'
F = 'fill="{b}" stroke="none"'

ICONS = {
    # Zwischenablage
    "copy": f'<rect x="8" y="8" width="12" height="12" rx="2" {L}/><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3" {L}/>',
    "paste": f'<rect x="5" y="4" width="14" height="17" rx="2" {L}/><rect x="9" y="2.5" width="6" height="3.5" rx="1" {X}/><path d="M9 11h6M9 15h4" {L}/>',
    "delete": f'<path d="M6 6l12 12M18 6L6 18" {X}/>',
    "group": f'<rect x="3" y="3" width="18" height="18" rx="2" stroke-dasharray="3 2" {L}/><rect x="6" y="6" width="6" height="6" {X}/><rect x="12" y="12" width="6" height="6" {X}/>',
    "ungroup": f'<rect x="3" y="3" width="8" height="8" {L}/><rect x="13" y="13" width="8" height="8" {L}/><path d="M14 4l6 6M20 4l-6 6" {X}/>',
    "add": f'<path d="M12 5v14M5 12h14" {X}/>',
    # Handhabung
    "select": f'<rect x="4" y="4" width="16" height="16" stroke-dasharray="4 3" {X}/>',
    "move": f'<path d="M5 19V6M5 19h13" {L}/><path d="M5 6l-2.5 3M5 6l2.5 3M18 19l-3-2.5M18 19l-3 2.5" {X}/>',
    "pnp": f'<path d="M4 4h7v4a2 2 0 1 0 0 4v4H4z" {L}/><path d="M13 8h7v12h-7v-4a2 2 0 1 0 0-4z" {X}/>',
    "interact": f'<path d="M9 11V5a1.5 1.5 0 0 1 3 0v6M12 10a1.5 1.5 0 0 1 3 0v1.5M15 11a1.5 1.5 0 0 1 3 0v4a6 6 0 0 1-6 6h-1a5 5 0 0 1-4-2l-3-4a1.5 1.5 0 0 1 2.3-2L9 15" {L}/><path d="M5 4l2 2M3 8h2.5M17 3l-1.5 2" {X}/>',
    "jog": f'<path d="M9 11V5a1.5 1.5 0 0 1 3 0v6M12 10a1.5 1.5 0 0 1 3 0v1.5M15 11a1.5 1.5 0 0 1 3 0v4a6 6 0 0 1-6 6h-1a5 5 0 0 1-4-2l-3-4a1.5 1.5 0 0 1 2.3-2L9 15" {L}/><path d="M3 4a6 6 0 0 1 6-1M21 4a6 6 0 0 0-6-1" {X}/>',
    # Werkzeuge
    "measure": f'<path d="M3 7h18M3 7l3-3M3 7l3 3M21 7l-3-3M21 7l-3 3" {X}/><rect x="3" y="13" width="18" height="7" rx="1" {L}/><path d="M7 13v3M11 13v4M15 13v3M19 13v3" {L}/>',
    "snap": f'<circle cx="16" cy="8" r="4" {L}/><path d="M4 20l8-8" {X}/><path d="M4 20h5M4 20v-5" {X}/>',
    "align": f'<path d="M4 20L20 4" {L}/><path d="M8 20l12-12M4 16L16 4" stroke-dasharray="2 2" {X}/>',
    "dim_linear": f'<path d="M4 8v8M20 8v8M4 12h16M4 12l3-2M4 12l3 2M20 12l-3-2M20 12l-3 2" {X}/>',
    "dim_angle": f'<path d="M4 20h16M4 20L16 6" {L}/><path d="M11 20a7 7 0 0 0-2.2-5.3" {X}/>',
    # Verbinden
    "interfaces": f'<circle cx="6" cy="6" r="2.5" {X}/><circle cx="18" cy="6" r="2.5" {X}/><circle cx="12" cy="18" r="2.5" {X}/><path d="M8 7.5l3 8M16 7.5l-3 8" {L}/>',
    "signals": f'<path d="M13 2L5 13h6l-1 9 8-11h-6z" {X}/>',
    "attach": f'<rect x="3" y="12" width="8" height="8" {L}/><rect x="13" y="4" width="8" height="8" {X}/><path d="M11 16h4v-4" {L}/>',
    "detach": f'<rect x="3" y="12" width="8" height="8" {L}/><rect x="13" y="4" width="8" height="8" {L}/><path d="M12 9l3 3M15 9l-3 3" {X}/>',
    # Import/Export
    "geometry": f'<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z" {L}/><path d="M12 12l8-4.5M12 12v9M12 12L4 7.5" {L}/><path d="M17 2v4M15 4h4" {X}/>',
    "import": f'<path d="M12 3v11M8 10l4 4 4-4" {X}/><path d="M4 15v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4" {L}/>',
    "export": f'<path d="M12 14V3M8 7l4-4 4 4" {X}/><path d="M4 15v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4" {L}/>',
    "stl": f'<path d="M6 3h9l4 4v14H6z" {L}/><path d="M9 17l3-6 3 6z" {X}/>',
    "image": f'<rect x="3" y="5" width="18" height="14" rx="2" {L}/><circle cx="9" cy="10" r="1.8" {X}/><path d="M4 18l6-5 4 3 3-2 4 4" {X}/>',
    "camera": f'<rect x="3" y="7" width="13" height="11" rx="2" {L}/><path d="M16 11l5-3v9l-5-3z" {X}/><circle cx="9.5" cy="12.5" r="2.5" {X}/>',
    # Ursprung
    "origin": f'<circle cx="12" cy="12" r="7" {L}/><circle cx="12" cy="12" r="2" {F}/><path d="M12 2v4M12 18v4M2 12h4M18 12h4" {X}/>',
    "origin_move": f'<circle cx="12" cy="12" r="3" {L}/><path d="M12 2v6M12 16v6M2 12h6M16 12h6M12 2l-2 2M12 2l2 2M22 12l-2-2M22 12l-2 2" {X}/>',
    # Analyse
    "analysis": f'<circle cx="10" cy="10" r="6" {L}/><path d="M15 15l6 6" {X}/><path d="M7 11l2 2 4-5" {X}/>',
    "chart": f'<path d="M4 4v16h16" {L}/><path d="M7 15l4-5 3 3 5-7" {X}/>',
    "record": f'<circle cx="12" cy="12" r="8" {L}/><circle cx="12" cy="12" r="4" {F}/>',
    "trace": f'<path d="M3 17c3-8 6 2 9-6s6-4 9-6" {X}/><circle cx="3" cy="17" r="1.5" {L}/><circle cx="21" cy="5" r="1.5" {L}/>',
    # Modellierung
    "component_new": f'<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z" {L}/><path d="M12 9v6M9 12h6" {X}/>',
    "save": f'<path d="M5 3h11l3 3v15H5z" {L}/><rect x="8" y="3" width="7" height="5" {X}/><rect x="8" y="13" width="8" height="6" {L}/>',
    "save_as": f'<path d="M5 3h11l3 3v7M5 3v18h8" {L}/><rect x="8" y="3" width="7" height="5" {L}/><path d="M15 21l6-6-2-2-6 6v2z" {X}/>',
    "link": f'<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1" {L}/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" {X}/>',
    "features": f'<path d="M7 3h10l4 6-9 12L3 9z" {L}/><path d="M3 9h18M12 21L8.5 9 12 3l3.5 6z" {X}/>',
    "tools": f'<path d="M14.5 6.5a4 4 0 0 0 5 5L12 19a2.1 2.1 0 0 1-3-3z" {L}/><path d="M4 4l6 6M4 4l2 6 4-2" {X}/>',
    "behavior": f'<circle cx="12" cy="12" r="3.2" {X}/><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M5.3 18.7l2.1-2.1M16.6 7.4l2.1-2.1" {L}/>',
    "properties": f'<path d="M4 6h16M4 12h16M4 18h16" {L}/><circle cx="9" cy="6" r="2" {F}/><circle cx="15" cy="12" r="2" {F}/><circle cx="7" cy="18" r="2" {F}/>',
    "wizard": f'<path d="M5 3h14v18l-7-4-7 4z" {L}/><path d="M12 7l1 2 2 .3-1.5 1.4.4 2.1-1.9-1-1.9 1 .4-2.1L9 9.3l2-.3z" {X}/>',
    "assistant": f'<path d="M5 21v-5h14v5" {L}/><path d="M7 16V8h10v8" {L}/><path d="M12 2v3M8 4l1 2M16 4l-1 2" {X}/>',
    "hierarchy": f'<rect x="9" y="3" width="6" height="5" {X}/><rect x="3" y="16" width="6" height="5" {L}/><rect x="15" y="16" width="6" height="5" {L}/><path d="M12 8v4H6v4M12 12h6v4" {L}/>',
    # Programm
    "robot_frame": f'<path d="M4 20h16" {L}/><path d="M8 20v-4h8v4M12 16V9l5-4" {L}/><path d="M4 4v6M4 4h6M4 4l5 5" {X}/>',
    "robot_swap": f'<path d="M7 20h6M10 20v-4l4-6" {L}/><path d="M16 4h5v5M21 4l-5 5M8 9H3V4M3 9l5-5" {X}/>',
    "sim_config": f'<circle cx="12" cy="12" r="8" {L}/><path d="M12 7v5l3 2" {X}/>',
    "teach_overlay": f'<rect x="3" y="4" width="18" height="13" rx="2" {L}/><path d="M7 21h10M12 17v4" {L}/><path d="M7 9h6M7 12h4" {X}/>',
    "collision": f'<rect x="3" y="8" width="8" height="8" {L}/><rect x="11" y="6" width="9" height="9" {L}/><path d="M11 10l2 2-2 2" {X}/><path d="M15 3l1 2M19 4l-1 2" {X}/>',
    "limits": f'<path d="M5 19a9 9 0 1 1 14 0" {L}/><path d="M12 12l5-4" {X}/><path d="M5 19l2-1M19 19l-2-1" {X}/>',
    # Konfiguration
    "io": f'<path d="M3 7h6M3 12h6M3 17h6" {X}/><rect x="9" y="4" width="6" height="16" rx="1" {L}/><path d="M15 7h6M15 12h6M15 17h6" {L}/>',
    "io_overview": f'<rect x="3" y="4" width="7" height="6" {L}/><rect x="14" y="4" width="7" height="6" {L}/><rect x="8.5" y="15" width="7" height="6" {L}/><path d="M6.5 10v2.5h11V10M12 12.5V15" {X}/>',
    "device_catalog": f'<path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z" {L}/><path d="M4 21a2 2 0 0 1 2-2h13v2" {L}/><path d="M9 8h6M9 11h4" {X}/>',
    "topology": f'<rect x="9" y="3" width="6" height="4" {L}/><rect x="3" y="17" width="5" height="4" {L}/><rect x="9.5" y="17" width="5" height="4" {L}/><rect x="16" y="17" width="5" height="4" {L}/><path d="M12 7v5M5.5 17v-5h13v5M12 12v5" {X}/>',
    "routing": f'<circle cx="5" cy="5" r="2" {X}/><circle cx="19" cy="19" r="2" {X}/><path d="M7 5h6a3 3 0 0 1 0 6h-2a3 3 0 0 0 0 6h6" {L}/>',
    "drive": f'<rect x="4" y="3" width="11" height="18" rx="1" {L}/><path d="M7 7h5M7 10h5" {L}/><circle cx="17.5" cy="15" r="3.5" {X}/><path d="M17.5 13v2l1 1" {X}/>',
    "drive_suggest": f'<rect x="4" y="3" width="11" height="18" rx="1" {L}/><path d="M7 7h5M7 10h5" {L}/><path d="M17 12l1.2 2.4 2.6.4-1.9 1.8.5 2.6-2.4-1.3-2.4 1.3.5-2.6-1.9-1.8 2.6-.4z" {X}/>',
    "machine_data": f'<rect x="3" y="4" width="18" height="16" rx="2" {L}/><path d="M7 9h4M7 13h7M7 17h3" {L}/><circle cx="17" cy="9" r="2" {X}/>',
    "rcs": f'<path d="M6 3h9l4 4v14H6z" {L}/><path d="M9 13h6M9 16h6M12 9v4" {X}/>',
    "transfer": f'<rect x="3" y="5" width="8" height="10" rx="1" {L}/><rect x="15" y="9" width="6" height="10" rx="1" {L}/><path d="M9 18h6l-2-2M15 6H9l2 2" {X}/>',
    "refresh": f'<path d="M20 11a8 8 0 0 0-14-5l-2 2M4 13a8 8 0 0 0 14 5l2-2" {L}/><path d="M4 4v4h4M20 20v-4h-4" {X}/>',
    "keep": f'<path d="M12 3l7 3v6c0 5-3 8-7 9-4-1-7-4-7-9V6z" {L}/><path d="M9 12l2 2 4-4" {X}/>',
    "merge": f'<path d="M6 3v6a6 6 0 0 0 6 6h6" {L}/><path d="M18 3v6" {L}/><path d="M15 12l3 3-3 3" {X}/>',
    "network": f'<rect x="8" y="3" width="8" height="6" rx="1" {L}/><rect x="3" y="15" width="6" height="6" rx="1" {L}/><rect x="15" y="15" width="6" height="6" rx="1" {L}/><path d="M12 9v3M6 15v-3h12v3" {X}/>',
    "longtext": f'<path d="M5 3h14v18H5z" {L}/><path d="M8 7h8M8 10h8M8 13h5" {L}/><path d="M13 19l5-5 2 2-5 5h-2z" {X}/>',
    # Hilfe
    "help": f'<circle cx="12" cy="12" r="9" {L}/><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6V14" {X}/><circle cx="12" cy="17.5" r="1" {F}/>',
    "expert": f'<circle cx="11" cy="11" r="6" {L}/><path d="M15.5 15.5L21 21" {L}/><path d="M9 9a2 2 0 1 1 2.8 1.8c-.5.2-.8.7-.8 1.2" {X}/>',
    "api": f'<path d="M8 6l-5 6 5 6M16 6l5 6-5 6" {L}/><path d="M14 4l-4 16" {X}/>',
    "academy": f'<path d="M2 9l10-5 10 5-10 5z" {L}/><path d="M6 11v5c2 2 10 2 12 0v-5" {L}/><path d="M22 9v6" {X}/>',
    "forum": f'<path d="M4 4h12v9H8l-4 3z" {L}/><path d="M18 8h2v10l-3-2h-7v-3" {X}/>',
    "blog": f'<path d="M4 20l1-5L16 4l4 4L9 19z" {L}/><path d="M14 6l4 4" {X}/>',
    "bug": f'<rect x="7" y="8" width="10" height="12" rx="5" {L}/><path d="M12 8v12M7 13H3M21 13h-4M7 17l-3 2M17 17l3 2M9 5l1.5 2M15 5l-1.5 2" {X}/>',
    "vscode": f'<path d="M17 3l4 2v14l-4 2L7 12z" {L}/><path d="M7 12l-4-3M7 12l-4 3M17 3v18" {X}/>',
    "workflow": f'<rect x="3" y="3" width="7" height="5" rx="1" {X}/><rect x="14" y="10" width="7" height="5" rx="1" {L}/><rect x="3" y="16" width="7" height="5" rx="1" {L}/><path d="M10 5.5h3a2 2 0 0 1 2 2V10M14 12.5h-3a2 2 0 0 0-2 2V16" {L}/>',
    "search": f'<circle cx="10.5" cy="10.5" r="6" {L}/><path d="M15 15l6 6" {X}/>',
    # Datei / Steuerung
    "new": f'<path d="M6 3h9l4 4v14H6z" {L}/><path d="M12 10v7M8.5 13.5h7" {X}/>',
    "open": f'<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v1" {L}/><path d="M3 7v11h16l3-8H6z" {X}/>',
    "play": f'<path d="M7 4l13 8-13 8z" {F}/>',
    "pause": f'<rect x="6" y="4" width="4" height="16" rx="1" {F}/><rect x="14" y="4" width="4" height="16" rx="1" {F}/>',
    "stop": f'<rect x="5" y="5" width="14" height="14" rx="2" {F}/>',
    "step": f'<path d="M5 4l10 8-10 8z" {F}/><rect x="17" y="4" width="3" height="16" rx="1" {F}/>',
    "reset": f'<path d="M4 12a8 8 0 1 0 2.3-5.7L4 8.5" {L}/><path d="M4 3.5v5h5" {X}/>',
    "settings": f'<circle cx="12" cy="12" r="3" {X}/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" {L}/>',
    "update": f'<path d="M12 3v12M7 10l5 5 5-5" {X}/><path d="M4 19h16" {L}/>',
    "info": f'<circle cx="12" cy="12" r="9" {L}/><path d="M12 11v6" {X}/><circle cx="12" cy="7.5" r="1" {F}/>',
    "exit": f'<path d="M14 4h5v16h-5" {L}/><path d="M10 8l-4 4 4 4M6 12h10" {X}/>',
    "recent": f'<circle cx="12" cy="12" r="8" {L}/><path d="M12 8v4l3 2" {X}/>',
    "robot": f'<path d="M5 21h10M7 21v-3h6v3" {L}/><path d="M10 18v-6l6-5 3 3" {L}/><circle cx="10" cy="12" r="1.5" {X}/><circle cx="16" cy="7" r="1.5" {X}/><path d="M19 10l1.5 2.5" {X}/>',
    "process": f'<path d="M3 17c4-1 5-9 9-9s5 8 9 9" {X}/><circle cx="12" cy="8" r="2" {L}/><path d="M12 3v3" {L}/>',
    "layout": f'<rect x="3" y="3" width="18" height="18" rx="2" {L}/><path d="M3 9h18M9 9v12" {X}/>',
    "view_iso": f'<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z" {L}/><path d="M12 12l8-4.5M12 12v9M12 12L4 7.5" {X}/>',
    'undo': f'<path d="M8 5L3 10l5 5" {X}/><path d="M3 10h10a7 7 0 0 1 0 14" {L}/>',
    'redo': f'<path d="M16 5l5 5-5 5" {X}/><path d="M21 10H11a7 7 0 0 0 0 14" {L}/>',
}


def _svg(name, a, b):
    body = ICONS.get(name, ICONS["info"]).replace("{a}", a).replace("{b}", b)
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">{body}</svg>'


@lru_cache(maxsize=512)
def icon(name, size=32, dark=None, line=None, accent=None):
    """QIcon des Symbols; dark=True fuer dunkle Flaechen (helle Linien). Standard folgt dem Theme."""
    if dark is None:
        dark = theme.BRAND.get("dark_ui", False)
    a = line or ("#e8eef6" if dark else theme.BRAND["text"])
    b = accent or ("#5fb4ef" if dark else theme.BRAND["accent"])
    ic = QIcon()
    for s in (size, size * 2):
        pm = QPixmap(QSize(s, s))
        pm.fill(Qt.GlobalColor.transparent)
        r = QSvgRenderer(QByteArray(_svg(name, a, b).encode()))
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r.render(p)
        p.end()
        ic.addPixmap(pm)
    # abgeblendete Variante fuer deaktivierte Schaltflaechen
    pm = QPixmap(QSize(size, size))
    pm.fill(Qt.GlobalColor.transparent)
    r = QSvgRenderer(QByteArray(_svg(name, "#55678a", "#55678a").encode()))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    r.render(p)
    p.end()
    ic.addPixmap(pm, QIcon.Mode.Disabled)
    return ic
