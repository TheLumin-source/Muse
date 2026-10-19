# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Muse (onedir).

Build:  pyinstaller muse.spec --noconfirm
Output: dist/Muse/Muse.exe  (+ dist/Muse/_internal/...)
"""
from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = r"D:\Muse\app"

datas = [
    (ROOT + r"\frontend", "frontend"),
    (ROOT + r"\muse.png", "."),
    (ROOT + r"\muse.ico", "."),
]
binaries = []
hiddenimports = [
    "muse.app", "muse.store", "muse.links", "muse.livefiles",
    "muse.capture", "muse.code", "muse.export", "muse.templates",
    "muse.updater", "muse.render", "muse.backup",
    # pywebview picks its Windows backend at runtime
    "webview.platforms.winforms", "webview.platforms.edgechromium",
    "clr",
    # FastAPI / uploads / mail helpers that import lazily
    "fastapi", "pydantic", "multipart", "python_multipart",
    "email.mime.text", "httpx", "fitz", "pymupdf",
]

# Pull in everything for packages that import lazily or ship native bits.
for pkg in ("uvicorn", "webview", "clr_loader", "pythonnet",
            "pystray", "pygments", "PIL", "fitz"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

hiddenimports += collect_submodules("uvicorn")
# Pygments discovers lexers/styles by import name, so bundle them all.
hiddenimports += collect_submodules("pygments.lexers")
hiddenimports += collect_submodules("pygments.styles")

a = Analysis(
    [ROOT + r"\run.py"],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "PyQt5", "PyQt6", "PySide2", "PySide6",
              "torch", "transformers", "numpy.f2py", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Muse",
    debug=False,
    strip=False,
    upx=False,
    console=False,           # windowed: no console window
    icon=ROOT + r"\muse.ico",
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Muse",
)
