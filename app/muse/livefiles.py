"""Cards that point at real files on this machine rather than copies of them.

A live card holds an absolute path. The picture you see is a cached thumbnail
that regenerates whenever the file's timestamp changes, so a card pointing at
a render output shows the current render, not the one you dropped in last week.

A watch card points at a folder and lists what is newest in it.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps

from . import platform, store

CACHE_DIR = store.DATA_ROOT / ".cache" / "thumbs"
THUMB_MAX = 480

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".avif"}
VIDEO_EXT = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
DESIGN_EXT = {".psd", ".ai", ".fig", ".xd", ".sketch", ".afdesign", ".afphoto"}
THREE_D_EXT = {".blend", ".fbx", ".obj", ".gltf", ".glb", ".usd", ".usdz", ".abc", ".stl"}
DOC_EXT = {".pdf"}                       # rendered to a preview via PyMuPDF
THUMBABLE = IMAGE_EXT | DOC_EXT          # kinds we can draw a real thumbnail for

# A window handle, set by run.py when we are running as a desktop app.
window = None


def kind_of(path: Path) -> str:
    if path.is_dir():
        return "folder"
    suffix = path.suffix.lower()
    if suffix in IMAGE_EXT:
        return "image"
    if suffix in DOC_EXT:
        return "pdf"
    if suffix in VIDEO_EXT:
        return "video"
    if suffix in THREE_D_EXT:
        return "3d"
    if suffix in DESIGN_EXT:
        return "design"
    return "file"


def describe(raw: str) -> dict:
    """What a card needs to know about a path, whether or not it still exists."""
    path = Path(raw)
    info = {
        "path": str(path),
        "name": path.name or str(path),
        "folder": str(path.parent),
        "exists": False,
        "kind": kind_of(path) if path.exists() else ("folder" if raw.endswith(("\\", "/")) else "file"),
        "size": 0,
        "mtime": 0.0,
        "modified": "",
    }
    try:
        stat = path.stat()
        info.update(
            exists=True,
            kind=kind_of(path),
            size=0 if path.is_dir() else stat.st_size,
            mtime=stat.st_mtime,
            modified=datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        )
    except OSError:
        pass
    return info


def listing(raw: str, kinds: str = "all", limit: int = 24) -> dict:
    """Newest files in a folder, most recent first."""
    folder = Path(raw)
    if not folder.is_dir():
        return {"exists": False, "files": [], "total": 0}

    wanted = None
    if kinds == "images":
        wanted = IMAGE_EXT
    elif kinds == "media":
        wanted = IMAGE_EXT | VIDEO_EXT

    entries = []
    try:
        with os.scandir(folder) as scan:
            for entry in scan:
                if entry.name.startswith("."):
                    continue
                if entry.is_dir():
                    continue
                if wanted and Path(entry.name).suffix.lower() not in wanted:
                    continue
                try:
                    stat = entry.stat()
                except OSError:
                    continue
                entries.append({
                    "path": entry.path,
                    "name": entry.name,
                    "kind": kind_of(Path(entry.path)),
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                })
    except OSError:
        return {"exists": False, "files": [], "total": 0}

    entries.sort(key=lambda item: item["mtime"], reverse=True)
    return {"exists": True, "files": entries[:limit], "total": len(entries)}


def thumbnail(raw: str, size: int = 320) -> Path | None:
    """A cached thumbnail, regenerated whenever the source file changes.

    Images go through Pillow; PDFs get their first page rendered with PyMuPDF.
    """
    path = Path(raw)
    try:
        stat = path.stat()
    except OSError:
        return None
    kind = kind_of(path)
    if kind not in ("image", "pdf"):
        return None

    size = max(64, min(THUMB_MAX, size))
    key = f"{path}|{stat.st_mtime_ns}|{stat.st_size}|{size}"
    name = hashlib.sha1(key.encode("utf-8", "replace")).hexdigest()[:20] + ".jpg"
    cached = CACHE_DIR / name
    if cached.exists():
        return cached

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        if kind == "pdf":
            _render_pdf(path, cached, size)
        else:
            with Image.open(path) as img:
                img = ImageOps.exif_transpose(img)
                img.thumbnail((size, size), Image.LANCZOS)
                if img.mode not in ("RGB", "L"):
                    img = img.convert("RGB")
                img.save(cached, "JPEG", quality=82)
    except Exception:
        return None
    return cached if cached.exists() else None


def _render_pdf(path: Path, dest: Path, size: int) -> None:
    """First page of a PDF to a JPEG, scaled so the long side is ~size."""
    import fitz  # PyMuPDF

    with fitz.open(path) as doc:
        page = doc[0]
        rect = page.rect
        scale = size / max(rect.width, rect.height, 1)
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        img.save(dest, "JPEG", quality=82)


def open_path(raw: str) -> bool:
    path = Path(raw)
    if not path.exists():
        return False
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606 - a path the user chose themselves
    else:
        subprocess.Popen(["xdg-open", str(path)])
    return True


def reveal_path(raw: str) -> bool:
    """Show the file in the file manager with it selected."""
    path = Path(raw)
    if not path.exists():
        return False
    return platform.reveal_in_file_manager(path)


def copy_to_clipboard(raw: str) -> bool:
    """Put the file on the clipboard so it can be pasted into other apps (the
    file manager, Photoshop, chat, email). The nearest thing to dragging it out,
    which a WebView cannot do. See platform.copy_file_to_clipboard for the
    per-platform mechanics and the Linux format caveat."""
    path = Path(raw)
    if not path.exists():
        return False
    return platform.copy_file_to_clipboard(path)


def save_copy(raw: str) -> bool:
    """Ask where to save, then copy the file there. Desktop-window only."""
    import shutil
    path = Path(raw)
    if not path.exists() or window is None:
        return False
    try:
        import webview
        dest = window.create_file_dialog(
            webview.SAVE_DIALOG, save_filename=path.name)
        if dest:
            target = dest if isinstance(dest, str) else dest[0]
            shutil.copy2(path, target)
            return True
    except Exception:
        pass
    return False


def pick(mode: str = "file") -> list[str]:
    """A real Windows file dialog, so we get an actual path back.

    The browser cannot give us one: an <input type=file> deliberately hides it.
    """
    if window is not None:
        try:
            import webview
            kinds = {
                "file": webview.OPEN_DIALOG,
                "files": webview.OPEN_DIALOG,
                "folder": webview.FOLDER_DIALOG,
            }
            result = window.create_file_dialog(
                kinds.get(mode, webview.OPEN_DIALOG),
                allow_multiple=(mode == "files"),
            )
            return [str(p) for p in (result or [])]
        except Exception:
            pass

    try:
        return _tk_pick(mode)
    except Exception:
        return []


def _tk_pick(mode: str) -> list[str]:
    """Fallback for when Muse is running in a browser rather than its own window."""
    import queue
    import threading
    import tkinter
    from tkinter import filedialog

    answer: queue.Queue = queue.Queue()

    def ask() -> None:
        root = tkinter.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        try:
            if mode == "folder":
                chosen = filedialog.askdirectory(parent=root)
                answer.put([chosen] if chosen else [])
            elif mode == "files":
                answer.put(list(filedialog.askopenfilenames(parent=root)))
            else:
                chosen = filedialog.askopenfilename(parent=root)
                answer.put([chosen] if chosen else [])
        finally:
            root.destroy()

    thread = threading.Thread(target=ask, daemon=True)
    thread.start()
    try:
        return answer.get(timeout=180)
    except queue.Empty:
        return []
