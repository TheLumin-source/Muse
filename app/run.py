"""Muse launcher.

    python run.py              desktop window
    python run.py --browser    open in your default browser instead
    python run.py --serve      just run the server (no window)
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import time
import webbrowser

import uvicorn

from muse import store
from muse.app import app


def fix_stdio() -> None:
    """Under pythonw.exe there is no console and sys.stdout/stderr are None,
    which makes uvicorn's logging blow up the moment it starts. Give them
    somewhere harmless to go."""
    for name in ("stdout", "stderr"):
        if getattr(sys, name, None) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))


def free_port(preferred: int) -> int:
    """Ask whether anything actually answers on the port, rather than trying to
    bind it: a port still in TIME_WAIT is free for our purposes."""
    try:
        with socket.create_connection(("127.0.0.1", preferred), timeout=0.3):
            pass
    except OSError:
        return preferred
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def serve(port: int) -> None:
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


def start_server(port: int) -> dict:
    """Run uvicorn on a background thread, keeping hold of anything it throws."""
    outcome: dict = {}

    def run() -> None:
        try:
            serve(port)
        except BaseException as exc:       # noqa: BLE001 - reported below
            outcome["error"] = exc

    threading.Thread(target=run, daemon=True).start()
    return outcome


def wait_until_serving(port: int, timeout: float = 25.0) -> bool:
    """Do not open a window at a port nothing is listening on yet."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.05)
    return False


def _report(message: str) -> None:
    """Launched from a shortcut there is no console, so say it in a dialog."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, message, "Muse", 0x10)
    except Exception:
        pass


def _announce_as_muse() -> None:
    """Make the window tell the desktop it is Muse.

    GTK builds WM_CLASS from the program name, so launched as run.py the window
    claims to be "run.py"/"Run.py". The desktop entry's StartupWMClass=Muse then
    matches nothing, the panel cannot work out which entry the window belongs
    to, and it falls back to a generic cog. Both halves have to be set before
    the window is realised. Cosmetic only, so it never fails a launch.
    """
    if sys.platform == "win32":
        return
    try:
        import gi
        gi.require_version("Gdk", "3.0")
        from gi.repository import GLib, Gdk
        GLib.set_prgname("muse")          # WM_CLASS instance
        Gdk.set_program_class("Muse")     # WM_CLASS class, what the panel matches

    except Exception:
        pass


def _apply_window_icon() -> None:
    """Give the window its own _NET_WM_ICON, so switchers and panels that do not
    resolve WM_CLASS still draw Muse rather than a generic cog.

    Neither obvious route works. webview.start(icon=...) assigns pywebview's
    state after it has already built the window, and the GTK backend reads that
    during creation. GTK's default icon list is not inherited by the
    ApplicationWindow pywebview builds; its own icon list stays empty. Setting
    it on the live window does take. That means reaching into pywebview's
    internals, so it is wrapped and purely cosmetic: a miss costs an icon, never
    a launch.

    Runs through start()'s own callback, which fires once the GUI loop is up.
    """
    if sys.platform == "win32":
        return
    icon = store.APP_DIR / "muse.png"
    if not icon.exists():
        return
    try:
        from gi.repository import GLib
        from webview.platforms.gtk import BrowserView

        def apply() -> bool:
            for view in BrowserView.instances.values():
                view.window.set_icon_from_file(str(icon))
            return False        # one shot

        GLib.idle_add(apply)
    except Exception:
        pass


def _webview_options() -> dict:
    """Extra arguments for webview.start().

    pywebview defaults to private_mode=True. On the GTK/WebKit backend that
    hands the page an ephemeral website data manager and no localStorage at
    all: the name is absent, so merely reading it throws ReferenceError and
    takes the frontend's module graph down with it. Muse keeps the theme, the
    open branches of the sidebar and the card clipboard there, so the window
    gets a real profile, in a dot-folder beside the boards.

    Storage is per origin, and the origin includes the port, so a launch that
    had to fall back off 8810 starts with an empty store. That is cosmetic.

    Windows stays on pywebview's defaults on purpose: WebView2 already gives
    the page working storage, and moving its user data folder would silently
    reset the theme and the sidebar for everyone already running Muse.
    """
    if sys.platform == "win32":
        return {}
    profile = store.DATA_ROOT / ".webview"
    profile.mkdir(parents=True, exist_ok=True)
    return {"private_mode": False, "storage_path": str(profile)}


def main() -> int:
    fix_stdio()
    # Stop the WebView from serving a stale copy of the app's own JS/CSS after an
    # update. WebView2 honours this env var; it must be set before the window is
    # created. Combined with the server's no-store headers, every launch loads
    # fresh code.
    if sys.platform == "win32":
        os.environ.setdefault("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS",
                              "--disable-http-cache --disk-cache-size=1")
    parser = argparse.ArgumentParser(description="Muse - a local visual board")
    parser.add_argument("--port", type=int, default=8810)
    parser.add_argument("--browser", action="store_true", help="open a browser tab")
    parser.add_argument("--serve", action="store_true", help="server only, no window")
    args = parser.parse_args()

    # Make a backup on launch if the newest one is more than a day old.
    from muse import backup
    backup.start_auto()

    port = free_port(args.port)
    url = f"http://127.0.0.1:{port}"

    if args.serve:
        print(f"Muse running at {url}")
        serve(port)
        return 0

    outcome = start_server(port)
    if not wait_until_serving(port):
        reason = outcome.get("error")
        message = f"Muse's server did not start on {url}.\n{reason!r}" if reason else \
                  f"Muse's server did not start on {url} in time."
        print(message)
        _report(message)
        return 1

    if args.browser:
        from muse import capture
        capture.start(url)
        webbrowser.open(url)
        print(f"Muse running at {url} - Ctrl+C to stop")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        return 0

    _announce_as_muse()

    try:
        import webview
    except ImportError:
        print("pywebview not installed; falling back to the browser.")
        webbrowser.open(url)
        input("Press Enter to stop Muse.")
        return 0

    window = webview.create_window("Muse", url, width=1440, height=900,
                                   min_size=(900, 600))
    # Live file cards need a real Windows file dialog to get real paths.
    from muse import capture, livefiles
    livefiles.window = window
    # Quick capture is OFF by default: a global hotkey plus synthetic keystrokes
    # is invasive and can trip other Windows shortcuts. Opt in by setting
    # "capture_enabled": true in Documents\Muse\settings.json.
    if store.read_settings().get("capture_enabled"):
        capture.start(url, quit_cb=window.destroy)

    webview.start(_apply_window_icon, **_webview_options())

    # The window has gone and the GUI loop is over. Let the page's final save
    # beacon reach the in-process server, then hard-exit so NOTHING lingers -
    # not the tray thread, not uvicorn. A lingering process is how an old copy
    # of Muse stays alive and serves stale code to the next launch.
    time.sleep(0.6)
    capture.stop()
    os._exit(0)         # guaranteed full quit; next launch is always fresh


if __name__ == "__main__":
    sys.exit(main())
