"""Zentrales Design der Ximaj RoboSim – abgestimmt auf das Erscheinungsbild von ximaj.com.

Farben, Schriften, Logo hier aendern – gilt fuer die ganze Anwendung.
Website-Stil (Stand 2026): dunkler Verlauf Navy #061E44 -> Schwarz (65°), halbtransparente Karten mit
16 px Radius, weisse Ueberschriften in Saira (500), Fliesstext Roboto, Knoepfe in Ximaj-Blau #0E74BB (8 px Radius).
"""
import os

BRAND = {
    "company": "Ximaj IT-Solutions",
    "product": "Ximaj RoboSim",
    "tagline": "Roboterzellen planen, programmieren, simulieren",
    "language": "XRL",
    "dark_ui": True,
    # Schriften (Fallbacks, falls Saira/Roboto nicht installiert sind)
    "font_head": "'Saira', 'Bahnschrift', 'Segoe UI', sans-serif",
    "font_body": "'Roboto', 'Segoe UI', sans-serif",
    "font_mono": "'Cascadia Mono', 'Consolas', monospace",
    # Grundflaechen (dunkel wie die Website)
    "bg": "#040c1b",
    "panel": "#081733",
    "panel_alt": "#0b1d3f",
    "card": "#0e2348",
    "field": "#06122a",
    "border": "#1d3a63",
    "border_soft": "#16305a",
    "text": "#eef3fa",
    "muted": "#98abc6",
    # Ximaj-Blau
    "accent": "#0e74bb",          # Primaer (Knoepfe)
    "accent_hover": "#1886d4",
    "accent_dark": "#5fb4ef",     # hervorgehobener Text auf dunklem Grund
    "link": "#5fb4ef",
    "accent_soft": "#123d6b",     # Auswahl/aktive Zeile
    # Navy (Verlauf wie Website-Hero)
    "navy": "#061e44",
    "navy_end": "#000000",
    "slate": "#020813",
    "on_navy": "#ffffff",
    # Status
    "warn": "#f59e0b",
    "error": "#ef4444",
    "ok": "#22c55e",
    # 3D
    "viewport_top": "#0a2552",
    "viewport_bottom": "#01060f",
    "floor": "#0b1d3c",
    "robot": "#0e74bb",           # Roboter in Ximaj-Blau
    "robot_trim": "#e6e9ee",      # Zierringe/Streifen
    "robot_joint": "#d9dee6",
    "grid": "#1d3a66",
    "grid_major": "#2b5590",
}

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
LOGO = os.path.join(ASSETS, "robosim-logo-light.png")       # Schriftzug fuer dunkle Flaechen
LOGO_DARK = os.path.join(ASSETS, "robosim-logo.png")        # Schriftzug fuer helle Flaechen
MARK = os.path.join(ASSETS, "robosim-mark.png")             # nur Symbol (Icon)
CHECK = os.path.join(ASSETS, "check.svg").replace("\\", "/")
_A = lambda n: os.path.join(ASSETS, n).replace("\\", "/")


def rgb(name):
    h = BRAND[name].lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def navy_gradient():
    """Website-Verlauf: 65°, Navy bis 40 %, dann zu Schwarz"""
    b = BRAND
    return f"qlineargradient(x1:0, y1:1, x2:1, y2:0.2, stop:0 {b['navy']}, stop:0.4 {b['navy']}, stop:1 {b['navy_end']})"


def stylesheet():
    b = BRAND
    grad = navy_gradient()
    card = "rgba(255,255,255,0.045)"
    line = "rgba(255,255,255,0.12)"
    hover = "rgba(255,255,255,0.10)"
    return f"""
    * {{ font-family: {b['font_body']}; font-size: 10pt; }}
    QWidget {{ color: {b['text']}; }}
    QMainWindow {{ background: {grad}; }}
    QDialog {{ background: {b['panel']}; color: {b['text']}; }}
    QMainWindow > QWidget, QDockWidget > QWidget, QTabWidget QWidget, QScrollArea {{ background: {b['panel']}; }}
    QToolBar::separator {{ background: {line}; width: 1px; margin: 4px 6px; }}

    /* Simulationsleiste */
    QToolBar#simbar {{ background: {b['panel_alt']}; border: none; border-bottom: 1px solid {b['border']}; padding: 4px 8px; spacing: 6px; }}
    QToolBar#simbar QLabel {{ background: transparent; color: {b['muted']}; }}
    QToolBar#simbar QLabel#simbrand {{ font-family: {b['font_head']}; font-size: 11pt; font-weight: 500; color: white; letter-spacing: 1px; }}
    QToolBar#simbar QPushButton {{ padding: 4px 12px; }}
    QToolBar#simbar QPushButton:flat {{ background: transparent; border: none; color: {b['muted']}; }}
    QToolBar#simbar QLineEdit {{ border-radius: 8px; padding: 4px 10px; }}
    QMainWindow > QStatusBar, QStatusBar {{ background: {b['slate']}; color: {b['muted']}; }}
    QStatusBar QLabel {{ color: {b['muted']}; background: transparent; }}

    QMainWindow::separator {{ background: {b['bg']}; width: 6px; height: 6px; }}
    QMainWindow::separator:hover {{ background: {b['accent']}; }}
    QMenu {{ background: {b['panel_alt']}; color: {b['text']}; border: 1px solid {b['border']}; border-radius: 8px; padding: 4px; }}
    QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}
    QMenu::item:selected {{ background: {b['accent_soft']}; color: white; }}
    QMenu::separator {{ height: 1px; background: {line}; margin: 4px 8px; }}

    /* Seitenbereiche */
    QDockWidget {{ color: white; font-family: {b['font_head']}; font-size: 11pt; }}
    QDockWidget::title {{ background: {grad}; padding: 8px 12px; text-align: left; }}
    QGroupBox {{ background: {card}; border: 1px solid {line}; border-radius: 16px; margin-top: 16px; padding: 12px 10px 10px 10px; }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 14px; padding: 0 6px; color: {b['accent_dark']};
        font-family: {b['font_head']}; font-size: 10.5pt; font-weight: 500; }}

    /* Knoepfe wie auf der Website */
    QPushButton, QToolButton {{ background: {hover}; color: {b['text']}; border: 1px solid {line}; border-radius: 8px; padding: 6px 14px; }}
    QPushButton:hover, QToolButton:hover {{ background: rgba(255,255,255,0.16); border-color: {b['accent']}; }}
    QPushButton:pressed, QToolButton:pressed, QToolButton:checked {{ background: {b['accent_soft']}; border-color: {b['accent']}; }}
    QPushButton:disabled {{ color: #5f7090; border-color: {b['border_soft']}; }}
    QPushButton#primary {{ background: {b['accent']}; color: white; border: 2px solid transparent; font-weight: 500; }}
    QPushButton#primary:hover {{ background: {b['accent_hover']}; }}
    QPushButton#primary:pressed {{ background: #075f96; }}
    QPushButton#danger {{ background: {b['error']}; color: white; border: 2px solid transparent; font-weight: 500; }}
    QPushButton#danger:hover {{ background: #dc2626; }}

    /* Eingabefelder */
    QLineEdit, QPlainTextEdit, QTextEdit, QTextBrowser, QSpinBox, QDoubleSpinBox, QComboBox, QListWidget, QTreeWidget, QTableWidget {{
        background: {b['field']}; color: {b['text']}; border: 1px solid {b['border']}; border-radius: 8px; padding: 3px 6px;
        selection-background-color: {b['accent_soft']}; selection-color: white; }}
    QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border: 1px solid {b['accent']}; }}
    QComboBox QAbstractItemView {{ background: {b['panel_alt']}; color: {b['text']}; border: 1px solid {b['border']};
        selection-background-color: {b['accent_soft']}; }}
    QAbstractSpinBox::up-button, QAbstractSpinBox::down-button, QComboBox::drop-down {{ background: transparent; border: none; width: 18px; }}
    QAbstractSpinBox::up-arrow {{ image: url({_A("arrow_up.svg")}); width: 10px; height: 7px; }}
    QAbstractSpinBox::down-arrow, QComboBox::down-arrow {{ image: url({_A("arrow_down.svg")}); width: 10px; height: 7px; }}
    QTreeView::branch:has-children:!has-siblings:closed, QTreeView::branch:closed:has-children:has-siblings {{ image: url({_A("chev_right.svg")}); }}
    QTreeView::branch:open:has-children:!has-siblings, QTreeView::branch:open:has-children:has-siblings {{ image: url({_A("chev_down.svg")}); }}
    QPlainTextEdit {{ font-family: {b['font_mono']}; }}
    QListWidget::item, QTreeWidget::item {{ padding: 4px 2px; border-radius: 6px; }}
    QListWidget::item:selected, QTreeWidget::item:selected {{ background: {b['accent_soft']}; color: white; }}
    QListWidget::item:hover, QTreeWidget::item:hover {{ background: rgba(255,255,255,0.06); }}
    QHeaderView, QHeaderView::section {{ background: {b['panel_alt']}; border: none; border-bottom: 1px solid {b['border']};
        padding: 5px; color: {b['muted']}; font-weight: 500; }}
    QTableWidget {{ gridline-color: {b['border_soft']}; }}
    QTableCornerButton::section {{ background: {b['panel_alt']}; border: none; }}
    QTreeView::branch {{ background: transparent; }}

    /* Reiter */
    QTabWidget::pane {{ border: 1px solid {line}; border-radius: 12px; background: {b['panel']}; top: -1px; }}
    QTabWidget::tab-bar {{ left: 0px; }}
    QTabWidget {{ background: {b['panel']}; }}
    QTabBar {{ background: {b['panel']}; }}
    QTabBar::tab {{ background: transparent; color: {b['muted']}; padding: 8px 14px; border: none;
        border-bottom: 2px solid transparent; font-family: {b['font_head']}; }}
    QTabBar::tab:hover {{ color: white; }}
    QTabBar::tab:selected {{ color: white; border-bottom: 2px solid {b['accent']}; }}
    QDockWidget QScrollArea, QDockWidget QScrollArea > QWidget > QWidget {{ background: {b['panel']}; }}

    QSlider::groove:horizontal {{ height: 6px; background: rgba(255,255,255,0.14); border-radius: 3px; }}
    QSlider::sub-page:horizontal {{ background: {b['accent']}; border-radius: 3px; }}
    QSlider::handle:horizontal {{ background: white; border: 2px solid {b['accent']}; width: 12px; margin: -5px 0; border-radius: 8px; }}
    QProgressBar {{ background: {b['field']}; border: 1px solid {b['border']}; border-radius: 8px; text-align: center; color: white; }}
    QProgressBar::chunk {{ background: {b['accent']}; border-radius: 7px; }}
    QCheckBox, QRadioButton {{ background: transparent; spacing: 6px; }}
    QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px; border: 1px solid #3d5f90; background: {b['field']}; }}
    QCheckBox::indicator:hover {{ border-color: {b['accent']}; }}
    QCheckBox::indicator:checked {{ background: {b['accent']}; border-color: {b['accent']}; image: url({CHECK}); }}
    QRadioButton::indicator {{ width: 14px; height: 14px; border-radius: 7px; border: 1px solid #3d5f90; background: {b['field']}; }}
    QRadioButton::indicator:hover {{ border-color: {b['accent']}; }}
    QRadioButton::indicator:checked {{ border: 1px solid {b['accent']};
        background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5, stop:0 {b['accent_dark']}, stop:0.5 {b['accent_dark']}, stop:0.62 {b['field']}, stop:1 {b['field']}); }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: rgba(255,255,255,0.18); border-radius: 4px; min-height: 28px; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
    QScrollBar::handle:horizontal {{ background: rgba(255,255,255,0.18); border-radius: 4px; min-width: 28px; }}
    QScrollBar::handle:hover {{ background: rgba(255,255,255,0.30); }}
    QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ width: 0; height: 0; background: transparent; }}
    QSplitter::handle {{ background: {b['border_soft']}; }}
    QToolTip {{ background: {b['panel_alt']}; color: white; border: 1px solid {b['accent']}; padding: 6px; border-radius: 6px; }}
    QLabel {{ background: transparent; }}
    QLabel#brand {{ font-family: {b['font_head']}; font-size: 15pt; font-weight: 500; color: white; }}
    QLabel#muted {{ color: {b['muted']}; }}
    QLabel#heading {{ font-family: {b['font_head']}; font-size: 13pt; font-weight: 500; color: white; }}
    QMessageBox {{ background: {b['panel']}; }}
    QGraphicsView {{ background: {b['field']}; border: 1px solid {b['border']}; border-radius: 8px; }}
    """
