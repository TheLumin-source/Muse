#!/usr/bin/env bash
# Muse launcher for Linux, the counterpart to Muse.bat.
#
#   ./muse.sh                    desktop window
#   ./muse.sh --browser          open in the default browser instead
#   ./muse.sh --serve            server only, no window
#   ./muse.sh --install-desktop  add Muse to the application menu
#
# Uses .venv/bin/python when a virtualenv sits beside this script, otherwise
# python3. Override with MUSE_PYTHON=/path/to/python.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

install_desktop() {
    local apps="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
    local target="$apps/muse.desktop"
    mkdir -p "$apps"
    sed -e "s|@INSTALL_DIR@|$HERE|g" "$HERE/packaging/muse.desktop" > "$target"
    chmod 644 "$target"
    # Without this the menu can take a login to notice the new entry.
    command -v update-desktop-database >/dev/null 2>&1 \
        && update-desktop-database "$apps" >/dev/null 2>&1 || true
    echo "Installed $target"
    echo "Muse should now appear in your application menu."
}

if [ "${1:-}" = "--install-desktop" ]; then
    install_desktop
    exit 0
fi

cd "$HERE"

PY="${MUSE_PYTHON:-}"
if [ -z "$PY" ]; then
    if [ -x "$HERE/.venv/bin/python" ]; then
        PY="$HERE/.venv/bin/python"
    else
        PY="python3"
    fi
fi

if ! command -v "$PY" >/dev/null 2>&1 && [ ! -x "$PY" ]; then
    echo "Muse: no usable Python found (tried '$PY')." >&2
    echo "Install python3, or set MUSE_PYTHON to an interpreter." >&2
    exit 1
fi

# WebKitGTK 2.42 and newer render through a DMA-BUF path that the Nvidia
# proprietary driver does not support, and the symptom is not an error: the
# window opens and stays blank or draws garbage. Turning that path off costs
# some GPU compositing and costs nothing on hardware that was working anyway,
# so only Nvidia gets it. /proc/driver/nvidia/version exists for the
# proprietary module and not for nouveau, which does not need this. An
# already-set value is left alone so anyone debugging can override it.
if [ -e /proc/driver/nvidia/version ] && [ -z "${WEBKIT_DISABLE_DMABUF_RENDERER:-}" ]; then
    WEBKIT_DISABLE_DMABUF_RENDERER=1
    export WEBKIT_DISABLE_DMABUF_RENDERER
fi

exec "$PY" run.py "$@"
