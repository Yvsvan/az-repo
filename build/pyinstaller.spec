# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec para BankParser — modo onedir, Windows x64.

Cómo construir localmente:
    pyinstaller build/pyinstaller.spec --noconfirm

El resultado queda en dist/BankParser/BankParser.exe (onedir).
Para distribuir, comprimir dist/BankParser/ en un zip.

Dependencias no-Python que se incluyen automáticamente:
  - customtkinter: sus themes JSON/PNG vía collect_data_files
  - tkinterdnd2: la DLL nativa win-x64/tkdnd*.dll
  - pdfplumber: sus recursos internos
"""

from __future__ import annotations

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------

SPEC_DIR = Path(SPECPATH)          # = az-repo/build/
ROOT = SPEC_DIR.parent             # = az-repo/
SRC = ROOT / "src"

# Ícono — si no existe se usa el de PyInstaller por defecto
_icon = str(SPEC_DIR / "icon.ico")
if not Path(_icon).exists():
    _icon = None

# ---------------------------------------------------------------------------
# Datos no-Python que deben ir en el bundle
# ---------------------------------------------------------------------------

datas = []
datas += collect_data_files("customtkinter")    # themes, PNG, JSON
datas += collect_data_files("tkinterdnd2")      # DLLs nativas por plataforma

# ---------------------------------------------------------------------------
# Hidden imports (módulos que PyInstaller no detecta por importación dinámica)
# ---------------------------------------------------------------------------

hiddenimports = []
hiddenimports += collect_submodules("customtkinter")
hiddenimports += [
    # openpyxl carga estilos y parsers dinámicamente
    "openpyxl.styles.stylesheet",
    "openpyxl.styles.fills",
    "openpyxl.styles.fonts",
    "openpyxl.styles.alignment",
    "openpyxl.reader.excel",
    "openpyxl.writer.excel",
    # pydantic v2 usa compiled modules opcionales
    "pydantic.deprecated.class_validators",
    "pydantic._internal._generate_schema",
    # packaging para comparar semver
    "packaging.version",
    # requests internals
    "requests.adapters",
    "urllib3",
    # pdfplumber / pdfminer
    "pdfplumber",
    "pdfminer",
    "pdfminer.high_level",
    "pdfminer.layout",
    "pdfminer.pdfdocument",
    "pdfminer.pdfpage",
    "pdfminer.pdfparser",
    # tkinterdnd2
    "tkinterdnd2",
    "tkinterdnd2.TkinterDnD",
]

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

block_cipher = None

a = Analysis(
    [str(SRC / "bank_parser" / "__main__.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # No incluir test frameworks en el exe
        "pytest",
        "pytest_cov",
        "black",
        "ruff",
        # No incluir IDE tools
        "IPython",
        "jupyter",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ---------------------------------------------------------------------------
# EXE (onedir: el .exe va junto a sus DLLs en dist/BankParser/)
# ---------------------------------------------------------------------------

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,   # onedir: binaries en carpeta aparte
    name="BankParser",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[
        "vcruntime140.dll",
        "python3*.dll",
        "tk*.dll",
        "tcl*.dll",
    ],
    console=False,           # Sin ventana de consola negra
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_icon,
    version=str(SPEC_DIR / "version_info.txt") if (SPEC_DIR / "version_info.txt").exists() else None,
)

# ---------------------------------------------------------------------------
# COLLECT (agrupa exe + binaries + datas en dist/BankParser/)
# ---------------------------------------------------------------------------

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[
        "vcruntime140.dll",
        "python3*.dll",
        "tk*.dll",
        "tcl*.dll",
    ],
    name="BankParser",
)
