"""Opt-in auto-update.

Your shop hosts a small manifest (latest.json), e.g.:

    {
      "version": "1.1.0",
      "url": "https://martinworks.org/muse/Muse-Setup.exe",
      "notes": "What changed in this release",
      "date": "2026-08-01"
    }

Muse checks it quietly on start (see UPDATE_URL in __init__.py). If a newer
version exists the app shows an "Update available" banner; nothing is ever
installed until the user clicks Update.

Installing: download the setup to temp, then hand off to a DETACHED cmd that
waits for this app to exit, runs the installer silently, and relaunches Muse.
The app has to be gone before the installer can replace its files, hence the
wait. Because the installer is fetched by the app (not a browser) it carries no
mark-of-the-web, so it does not trip SmartScreen.

Only meaningful in the installed (frozen) build; from source it just reports
whatever the manifest says and the apply step no-ops the relaunch.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

import httpx

from . import UPDATE_URL, __version__

# Windows process-creation flags. They must be zero on POSIX, where passing a
# non-zero creationflags raises. Applying an update is Windows-only anyway: it
# shells out to the Inno installer. Linux needs its own update path.
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0   # CREATE_NO_WINDOW
_DETACHED = 0x00000008 if sys.platform == "win32" else 0    # DETACHED_PROCESS
TMP_DIR = Path(tempfile.gettempdir())


def _parse(v: str) -> tuple:
    """'1.10.2' -> (1, 10, 2) so 1.10 sorts above 1.9."""
    out = []
    for part in str(v or "0").strip().split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        out.append(int(digits) if digits else 0)
    while len(out) < 3:
        out.append(0)
    return tuple(out[:3])


def check() -> dict:
    """Look up the manifest. Never raises - a failed check just reports no update."""
    current = __version__
    result = {"current": current, "available": False, "latest": current,
              "notes": "", "url": "", "date": "", "error": ""}
    try:
        with httpx.Client(timeout=8.0, follow_redirects=True) as client:
            response = client.get(UPDATE_URL, headers={"Cache-Control": "no-cache"})
            response.raise_for_status()
            data = response.json()
    except Exception as exc:  # noqa: BLE001 - offline / not published yet is fine
        result["error"] = str(exc)[:200]
        return result

    latest = str(data.get("version", "") or "")
    url = str(data.get("url", "") or "")
    result["latest"] = latest or current
    result["notes"] = str(data.get("notes", "") or "")
    result["date"] = str(data.get("date", "") or "")
    result["url"] = url
    if latest and url.lower().startswith("https://") and _parse(latest) > _parse(current):
        result["available"] = True
    return result


def download(url: str) -> Path:
    """Stream the installer to a temp file."""
    dest = TMP_DIR / f"Muse-Update-{uuid.uuid4().hex[:8]}.exe"
    with httpx.stream("GET", url, timeout=None, follow_redirects=True) as response:
        response.raise_for_status()
        with open(dest, "wb") as handle:
            for chunk in response.iter_bytes(1 << 20):
                handle.write(chunk)
    if dest.stat().st_size < 500_000:      # a real installer is far bigger
        dest.unlink(missing_ok=True)
        raise RuntimeError("The downloaded update looks incomplete.")
    return dest


def apply_and_restart(setup: Path) -> None:
    """Spawn a detached updater, then quit so the installer can replace our files."""
    if sys.platform != "win32":
        return
    exe = sys.executable if getattr(sys, "frozen", False) else ""
    relaunch = f'start "" "{exe}"' if exe else ""
    # wait for this process to close -> install silently -> reopen Muse
    cmd = (f'timeout /t 4 /nobreak >nul & '
           f'"{setup}" /VERYSILENT /SUPPRESSMSGBOXES /TASKS=desktopicon & {relaunch}')
    subprocess.Popen(["cmd", "/c", cmd],
                     creationflags=_DETACHED | _NO_WINDOW, close_fds=True)

    def _bye():
        time.sleep(1.5)      # let the HTTP response reach the UI first
        os._exit(0)

    threading.Thread(target=_bye, daemon=True).start()
