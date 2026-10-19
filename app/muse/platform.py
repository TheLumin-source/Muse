"""Platform-specific desktop integration, kept in one place.

Muse runs on Windows and Linux. Only three things genuinely differ between them:
showing a file in the file manager, putting a file on the clipboard, and finding
a font to draw with. Everything else in the app is already portable.

Every function here degrades to a False or None return rather than raising, so a
host missing the tool it wants is a feature that quietly does nothing, never a
crash. Callers already treat these as best-effort.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"
IS_LINUX = not IS_WINDOWS and not IS_MACOS

# Keeps a console window from flashing up behind the desktop app. Meaningless on
# POSIX, where a non-zero creationflags raises instead.
_NO_WINDOW = 0x08000000 if IS_WINDOWS else 0


def _run(cmd: list[str], stdin: bytes | None = None) -> bool:
    """Run a helper command, swallowing anything it throws."""
    try:
        proc = subprocess.run(
            cmd,
            input=stdin,
            check=False,
            capture_output=True,
            creationflags=_NO_WINDOW,
        )
        return proc.returncode == 0
    except (OSError, ValueError):
        return False


# --- where the user's own files live ----------------------------------------


def documents_dir() -> Path:
    """The user's Documents folder, as the desktop actually defines it.

    Windows and macOS keep it at ~/Documents. Linux lets the user move and
    translate it (~/Dokumente, ~/Documentos) and records the real location in the
    XDG user-dirs config, so ask xdg-user-dir rather than assuming a name that
    may not exist on this machine.
    """
    home = Path(os.path.expanduser("~"))

    if IS_LINUX and shutil.which("xdg-user-dir"):
        try:
            proc = subprocess.run(
                ["xdg-user-dir", "DOCUMENTS"],
                check=False, capture_output=True, text=True,
            )
            found = proc.stdout.strip()
            if proc.returncode == 0 and found:
                candidate = Path(found)
                # xdg-user-dir echoes $HOME back when the entry is unset, which
                # would scatter the app's folders across the home directory.
                if candidate != home:
                    return candidate
        except OSError:
            pass

    return home / "Documents"


# --- showing a file in the file manager -------------------------------------


def reveal_in_file_manager(path: Path) -> bool:
    """Open the containing folder with the file selected, where the platform can.

    Falls back to just opening the folder when selection is not available.
    """
    if not path.exists():
        return False

    if IS_WINDOWS:
        if path.is_dir():
            subprocess.Popen(["explorer", str(path)])
        else:
            # One string, not argv tokens: explorer's /select, does not accept a
            # separately quoted path and silently opens the wrong thing.
            subprocess.Popen(f'explorer /select,"{path}"')
        return True

    if IS_MACOS:
        return _run(["open", "-R", str(path)])

    # Linux. The freedesktop file-manager interface is the only portable way to
    # get the file *selected* rather than just opening its folder. Nautilus,
    # Dolphin, Nemo and Thunar all implement it; if none is running, gdbus fails
    # and we settle for opening the parent directory.
    target = path if path.is_dir() else path.parent
    if not path.is_dir() and shutil.which("gdbus"):
        uri = path.resolve().as_uri()
        if _run([
            "gdbus", "call", "--session",
            "--dest", "org.freedesktop.FileManager1",
            "--object-path", "/org/freedesktop/FileManager1",
            "--method", "org.freedesktop.FileManager1.ShowItems",
            f"['{uri}']", "",
        ]):
            return True

    if shutil.which("xdg-open"):
        return _run(["xdg-open", str(target)])
    return False


# --- putting a file on the clipboard ----------------------------------------


def copy_file_to_clipboard(path: Path) -> bool:
    """Put the file itself on the clipboard so it can be pasted into other apps.

    The nearest thing to dragging it out of the window, which a WebView cannot do.

    Linux caveat worth knowing: file managers disagree about clipboard formats.
    text/uri-list is the broadly understood one and works in Dolphin, Thunar and
    most chat and mail clients. Nautilus prefers its own private format and may
    paste the path as text instead of the file. That is a graceful degradation,
    not a failure.
    """
    if not path.exists():
        return False

    if IS_WINDOWS:
        # A single -Command string with the path as a PowerShell literal, doubling
        # any embedded quote. Passing it as separate argv tokens leaves a path with
        # spaces unquoted, which fails silently.
        literal = str(path).replace("'", "''")
        return _run([
            "powershell", "-NoProfile", "-Command",
            f"Set-Clipboard -LiteralPath '{literal}'",
        ])

    if IS_MACOS:
        script = f'set the clipboard to (POSIX file "{path}")'
        return _run(["osascript", "-e", script])

    # Linux: one trailing CRLF, per the text/uri-list spec.
    payload = (path.resolve().as_uri() + "\r\n").encode("utf-8")

    if os.environ.get("WAYLAND_DISPLAY") and shutil.which("wl-copy"):
        if _run(["wl-copy", "--type", "text/uri-list"], stdin=payload):
            return True

    if shutil.which("xclip"):
        return _run(
            ["xclip", "-selection", "clipboard", "-t", "text/uri-list", "-i"],
            stdin=payload,
        )

    # Wayland session with no xclip, or an X11 session with only wl-copy present.
    if shutil.which("wl-copy"):
        return _run(["wl-copy", "--type", "text/uri-list"], stdin=payload)
    return False


# --- finding a font to draw with --------------------------------------------

# render.py asks for a role, not a filename, so each platform can answer with
# whatever it actually has.
_WINDOWS_FONTS = {
    "sans": "segoeui.ttf",
    "sans-bold": "segoeuib.ttf",
    "mono": "consola.ttf",
}

_FONTCONFIG_PATTERNS = {
    "sans": "sans-serif",
    "sans-bold": "sans-serif:bold",
    "mono": "monospace",
}

# Used when fontconfig is unavailable. Ordered by how likely the distro is to
# ship it; DejaVu is on essentially every desktop install.
_LINUX_FALLBACKS = {
    "sans": [
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/liberation/LiberationSans-Regular.ttf",
    ],
    "sans-bold": [
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/noto/NotoSans-Bold.ttf",
        "/usr/share/fonts/liberation/LiberationSans-Bold.ttf",
    ],
    "mono": [
        "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
        "/usr/share/fonts/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/noto/NotoSansMono-Regular.ttf",
        "/usr/share/fonts/liberation/LiberationMono-Regular.ttf",
    ],
}

_MACOS_FALLBACKS = {
    "sans": ["/System/Library/Fonts/Helvetica.ttc", "/Library/Fonts/Arial.ttf"],
    "sans-bold": ["/System/Library/Fonts/Helvetica.ttc", "/Library/Fonts/Arial Bold.ttf"],
    "mono": ["/System/Library/Fonts/Menlo.ttc", "/System/Library/Fonts/Courier.ttc"],
}


@lru_cache(maxsize=8)
def font_path(role: str) -> str | None:
    """Resolve a font role to a file on disk, or None to use Pillow's default.

    Cached: board export calls this per render and fc-match is a subprocess.
    """
    if IS_WINDOWS:
        name = _WINDOWS_FONTS.get(role)
        if name:
            candidate = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name
            if candidate.exists():
                return str(candidate)
        return None

    # fontconfig knows what is actually installed and respects the user's own
    # font preferences, so ask it before guessing at paths.
    pattern = _FONTCONFIG_PATTERNS.get(role)
    if pattern and shutil.which("fc-match"):
        try:
            proc = subprocess.run(
                ["fc-match", "-f", "%{file}", pattern],
                check=False, capture_output=True, text=True,
            )
            found = proc.stdout.strip()
            if proc.returncode == 0 and found and Path(found).exists():
                return found
        except OSError:
            pass

    table = _MACOS_FALLBACKS if IS_MACOS else _LINUX_FALLBACKS
    for candidate in table.get(role, []):
        if Path(candidate).exists():
            return candidate
    return None
