"""Erzeugt build/version_info.txt (Windows-Dateieigenschaften der EXE) aus version.py."""
import os, sys
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "ximaj_robosim"))
from version import VERSION
v = [int(x) for x in VERSION.split(".")] + [0]
t = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers=({v[0]}, {v[1]}, {v[2]}, 0), prodvers=({v[0]}, {v[1]}, {v[2]}, 0),
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040704B0', [
      StringStruct('CompanyName', 'Ximaj IT-Solutions'),
      StringStruct('FileDescription', 'Ximaj RoboSim - Roboterzellen planen, programmieren, simulieren'),
      StringStruct('FileVersion', '{VERSION}'),
      StringStruct('InternalName', 'XimajRoboSim'),
      StringStruct('LegalCopyright', '(c) Ximaj IT-Solutions'),
      StringStruct('OriginalFilename', 'XimajRoboSim.exe'),
      StringStruct('ProductName', 'Ximaj RoboSim'),
      StringStruct('ProductVersion', '{VERSION}')])]),
    VarFileInfo([VarStruct('Translation', [1031, 1200])])
  ]
)
"""
os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)
open(os.path.join(ROOT, "build", "version_info.txt"), "w", encoding="utf8").write(t)
print(VERSION)
