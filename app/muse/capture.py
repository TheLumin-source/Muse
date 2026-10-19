"""Quick capture: press the hotkey anywhere in Windows, snip a region, and it
lands on whichever board you have open.

How it works, because none of it is obvious:

- A global hotkey (default Win+Shift+T, to sit beside Windows' own Win+Shift+S)
  is registered with the OS, so it fires from any app.
- Firing it presses Win+Shift+S *for* you, which brings up Windows' own region
  snip - the one UI that already handles multiple monitors and DPI properly.
- The snip puts a PNG on the clipboard. We watch the clipboard sequence number,
  lift the image off, and drop it into D:\\Muse\\.inbox.
- The open Muse page polls the inbox every couple of seconds and pins whatever
  arrives to the current board. If no board is open, captures simply wait.

Everything here is Windows-only by design and does nothing on other platforms.
"""

from __future__ import annotations

import secrets
import sys
import threading
import time
import webbrowser
from datetime import datetime
from pathlib import Path

# ctypes.wintypes does not exist off Windows and raises on import. app.py imports
# this module unconditionally, so importing it at top level took the whole app
# down on Linux before start() ever got the chance to bow out.
if sys.platform == "win32":
    import ctypes
    import ctypes.wintypes

from . import store

INBOX = store.DATA_ROOT / ".inbox"
DEFAULT_HOTKEY = "win+shift+t"
FALLBACK_HOTKEY = "ctrl+alt+t"

# What the status endpoint reports.
state = {"armed": False, "hotkey": "", "last_error": ""}

_icon = None

_MODS = {"alt": 1, "ctrl": 2, "control": 2, "shift": 4, "win": 8}
_MOD_NOREPEAT = 0x4000
_WM_HOTKEY = 0x0312
_KEYEVENTF_KEYUP = 0x0002
_VK = {"win": 0x5B, "shift": 0x10, "ctrl": 0x11, "alt": 0x12, "s": 0x53,
       "printscreen": 0x2C}


def _parse(spec: str) -> tuple[int, int | None]:
    mods, vk = 0, None
    for part in spec.lower().split("+"):
        part = part.strip()
        if part in _MODS:
            mods |= _MODS[part]
        elif part == "printscreen":
            vk = _VK["printscreen"]
        elif len(part) == 1 and part.isalnum():
            vk = ord(part.upper())
    return mods, vk


def _user32():
    return ctypes.windll.user32


def _press_snip_keys() -> None:
    """Press Win+Shift+S on the user's behalf."""
    u = _user32()
    # Give the user a beat to let go of the hotkey keys, or the synthetic
    # presses combine with the held ones into nonsense.
    time.sleep(0.25)
    for vk in (_VK["win"], _VK["shift"], _VK["s"]):
        u.keybd_event(vk, 0, 0, 0)
    for vk in (_VK["s"], _VK["shift"], _VK["win"]):
        u.keybd_event(vk, 0, _KEYEVENTF_KEYUP, 0)


def snip_now() -> Path | None:
    """Trigger the OS snip and wait for the image it puts on the clipboard."""
    from PIL import Image, ImageGrab

    u = _user32()
    sequence = u.GetClipboardSequenceNumber()
    _press_snip_keys()

    deadline = time.monotonic() + 120     # the user may take their time
    while time.monotonic() < deadline:
        time.sleep(0.3)
        current = u.GetClipboardSequenceNumber()
        if current == sequence:
            continue
        sequence = current
        try:
            grabbed = ImageGrab.grabclipboard()
        except Exception:
            continue
        if isinstance(grabbed, Image.Image):
            INBOX.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%H%M%S")
            path = INBOX / f"capture_{stamp}_{secrets.token_hex(3)}.png"
            grabbed.save(path, "PNG")
            return path
        # The clipboard changed to something that is not an image (the user
        # copied text mid-snip, say). Keep watching until the deadline.
    return None


def _hotkey_loop() -> None:
    u = _user32()
    registered = None
    for spec in (store.read_settings().get("capture_hotkey") or DEFAULT_HOTKEY,
                 FALLBACK_HOTKEY):
        mods, vk = _parse(spec)
        if vk and u.RegisterHotKey(None, 1, mods | _MOD_NOREPEAT, vk):
            registered = spec
            break
    if not registered:
        state["last_error"] = "no hotkey could be registered"
        return

    state.update(armed=True, hotkey=registered)
    msg = ctypes.wintypes.MSG()
    while u.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
        if msg.message == _WM_HOTKEY:
            threading.Thread(target=snip_now, daemon=True).start()


def pending() -> list[dict]:
    """Captures waiting to be pinned, oldest first."""
    if not INBOX.exists():
        return []
    files = []
    for entry in INBOX.glob("capture_*.png"):
        try:
            files.append({"name": entry.name, "ts": entry.stat().st_mtime})
        except OSError:
            continue
    files.sort(key=lambda f: f["ts"])
    return files


def claim(name: str, project_id: str, board_id: str) -> dict | None:
    """Move one capture out of the inbox and into a board's assets."""
    if "/" in name or "\\" in name or not name.startswith("capture_"):
        raise ValueError("bad capture name")
    path = INBOX / name
    try:
        data = path.read_bytes()
        path.unlink()
    except OSError:
        return None      # someone else claimed it first
    from PIL import Image
    import io
    src = store.save_asset(project_id, board_id, name, data)
    info = {"src": src, "name": name, "size": len(data), "kind": "image"}
    try:
        with Image.open(io.BytesIO(data)) as img:
            info.update(nw=img.width, nh=img.height)
    except Exception:
        pass
    return info


def _start_tray(url: str, quit_cb) -> None:
    global _icon
    try:
        import pystray
        from PIL import Image
        base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
        image = Image.open(base / "muse.png")

        def open_muse(icon, item):
            webbrowser.open(url)

        def capture_region(icon, item):
            threading.Thread(target=snip_now, daemon=True).start()

        def quit_app(icon, item):
            icon.stop()
            quit_cb()

        icon = pystray.Icon(
            "Muse", image, "Muse",
            menu=pystray.Menu(
                pystray.MenuItem("Open Muse", open_muse, default=True),
                pystray.MenuItem(lambda item: f"Capture region ({state['hotkey'] or 'hotkey off'})",
                                 capture_region),
                pystray.MenuItem("Quit Muse", quit_app),
            ),
        )
        _icon = icon
        icon.run_detached()
    except Exception as exc:
        state["last_error"] = f"tray: {exc!r}"


def stop() -> None:
    """Take the tray icon down; its thread is not a daemon and would otherwise
    keep the process alive forever after the window closes."""
    global _icon
    if _icon is not None:
        try:
            _icon.stop()
        except Exception:
            pass
        _icon = None


def start(url: str, quit_cb=None) -> None:
    """Arm the hotkey and show the tray icon. Windows only; harmless elsewhere."""
    if sys.platform != "win32":
        return
    threading.Thread(target=_hotkey_loop, daemon=True).start()
    _start_tray(url, quit_cb or (lambda: None))
