# -*- mode: python ; coding: utf-8 -*-
# ============================================================
# Spec PyInstaller — CNPS Disa Manager
# Générer l'exe : pyinstaller disa_manager.spec
# ============================================================

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# ---------- Ressources à embarquer dans le bundle ----------
datas = [
    # Schéma SQL (lecture seule, dans _MEIPASS)
    ("db/schema.sql",                     "db"),

    # Images de l'interface (logo, bâtiment CNPS)
    ("src/ui/images",                     "ui/images"),

    # Feuilles de style Qt
    ("src/ui/style.qss",                  "ui"),
    ("src/ui/pages/style.qss",            "ui/pages"),

    # Icônes SVG de la page Accueil
    ("src/ui/pages/home/icons",           "ui/pages/home/icons"),
]

# Pandas et openpyxl ont des fichiers de données internes
datas += collect_data_files("pandas")
datas += collect_data_files("openpyxl")

# ---------- Imports cachés (non détectés automatiquement) ----------
hiddenimports = [
    # PySide6
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PySide6.QtSql",

    # pandas / numpy (sous-modules souvent manquants)
    *collect_submodules("pandas"),
    "numpy",
    "numpy.core._multiarray_umath",

    # openpyxl
    *collect_submodules("openpyxl"),
]

# ---------- Analyse ----------
a = Analysis(
    ["app.py"],
    # pathex=['src'] permet d'importer db, ui, core, services sans préfixe src.
    pathex=["src"],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "scipy", "PIL"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ---------- Exécutable (mode dossier — recommandé pour PySide6) ----------
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,          # onedir : les binaires sont dans le dossier
    name="DisaManager",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                      # UPX désactivé : évite les faux positifs antivirus Windows
    console=False,                  # pas de fenêtre console noire
    icon=None,                      # remplacer par "src/ui/images/cnps_logo.ico" si disponible
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,                      # UPX désactivé : évite les faux positifs antivirus Windows
    upx_exclude=[],
    name="DisaManager",             # -> dist/DisaManager/
)
