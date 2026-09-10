# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, copy_metadata


streamlit_data, streamlit_binaries, streamlit_hidden = collect_all("streamlit")
metadata = []
for package in ("streamlit", "altair", "pandas", "pydeck"):
    metadata += copy_metadata(package)

analysis = Analysis(
    ["packaging/windows_launcher.py"],
    pathex=["."],
    binaries=streamlit_binaries,
    datas=streamlit_data
    + metadata
    + [
        ("app.py", "."),
        ("data/raw/debugpath_knowledge.json", "data/raw"),
        ("data/raw/debugpath_evidence.json", "data/raw"),
        (".streamlit/config.toml", ".streamlit"),
    ],
    hiddenimports=streamlit_hidden,
    excludes=["matplotlib", "networkx", "neo4j", "openai", "pytest", "tqdm"],
    noarchive=False,
)
pyz = PYZ(analysis.pure)

executable = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="DebugPath",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
