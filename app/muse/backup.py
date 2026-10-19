"""Backups. The whole point of Muse is that your work is safe and it's yours, so
we keep real copies, not just the per-project trash.

A backup is a single zip of everything under Projects (plus settings.json),
written to Documents\\Muse\\Backups. Muse makes one automatically on launch if
the newest backup is more than a day old, and keeps the most recent handful. You
can also make one on demand.
"""

from __future__ import annotations

import threading
import time
import zipfile
from datetime import datetime
from pathlib import Path

from . import store

BACKUP_DIR = store.DATA_ROOT / "Backups"
KEEP = 10
MIN_INTERVAL_HOURS = 20
PATTERN = "Muse-backup-*.zip"


def _has_content() -> bool:
    return store.PROJECTS_DIR.exists() and any(store.PROJECTS_DIR.iterdir())


def _existing() -> list[Path]:
    return list(BACKUP_DIR.glob(PATTERN)) if BACKUP_DIR.exists() else []


def list_backups() -> list[dict]:
    out = []
    for f in sorted(_existing(), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            st = f.stat()
            out.append({
                "name": f.name,
                "size": st.st_size,
                "when": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
            })
        except OSError:
            continue
    return out


def backup_now() -> Path | None:
    """Zip Projects + settings atomically. Returns the file, or None if empty."""
    if not _has_content():
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    dest = BACKUP_DIR / f"Muse-backup-{stamp}.zip"
    tmp = dest.with_suffix(".part")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for path in store.PROJECTS_DIR.rglob("*"):
            if path.is_file():
                z.write(path, path.relative_to(store.DATA_ROOT))
        if store.SETTINGS_FILE.exists():
            z.write(store.SETTINGS_FILE, store.SETTINGS_FILE.name)
    tmp.replace(dest)
    _prune()
    return dest


def _prune() -> None:
    for old in sorted(_existing(), key=lambda p: p.stat().st_mtime, reverse=True)[KEEP:]:
        try:
            old.unlink()
        except OSError:
            pass


def _last_time() -> float:
    return max((f.stat().st_mtime for f in _existing()), default=0.0)


def auto_backup_if_due() -> None:
    if not _has_content():
        return
    if time.time() - _last_time() < MIN_INTERVAL_HOURS * 3600:
        return
    try:
        backup_now()
    except Exception:
        pass  # a failed backup must never stop the app from starting


def start_auto() -> None:
    """Fire the launch backup on a background thread so startup stays instant."""
    threading.Thread(target=auto_backup_if_due, daemon=True).start()
