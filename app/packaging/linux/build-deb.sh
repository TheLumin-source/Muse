#!/usr/bin/env bash
# Build a Debian package of Muse, for Debian, Ubuntu and Mint.
#
#   app/packaging/linux/build-deb.sh      ->  out/muse_<version>_amd64.deb
#
# The counterpart to build.ps1, but there is no PyInstaller step. On Linux the
# window is WebKitGTK reached through the distro's PyGObject, and neither
# freezes usefully, so the package ships the source and declares those two as
# dependencies. Everything pip-only is vendored beside the app, so installing
# needs no network and no pip, and the app never has to share a site-packages
# with anything else.
#
# Before a release: bump __version__ in muse/__init__.py. That single number is
# what names the file and fills in the control file.
#
# The compiled wheels in vendor/ are built for the Python running this script,
# so the package declares the matching python3 version and will refuse to
# install where that would not work. Build it on the oldest distro you mean to
# support.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP="$(cd "$HERE/../.." && pwd)"          # .../Muse/app
ROOT="$(cd "$APP/.." && pwd)"             # .../Muse
OUT="$ROOT/out"
STAGE="$APP/build/deb"

PYTHON="${MUSE_BUILD_PYTHON:-python3}"

say() { printf '\n== %s ==\n' "$1"; }

# --- version, from the one place that holds it ------------------------------

VERSION="$(sed -n 's/^__version__ = "\([^"]*\)"/\1/p' "$APP/muse/__init__.py")"
[ -n "$VERSION" ] || { echo "Could not read __version__ from muse/__init__.py" >&2; exit 1; }

PYVER="$("$PYTHON" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
PYNEXT="$("$PYTHON" -c 'import sys; print("%d.%d" % (sys.version_info[0], sys.version_info[1] + 1))')"
ARCH="$(dpkg --print-architecture)"
PKG="muse-board_${VERSION}_${ARCH}.deb"

echo "Building Muse $VERSION for $ARCH, against Python $PYVER"

# --- 1/4 stage the app ------------------------------------------------------

say "1/4  staging"
rm -rf "$STAGE"
install -d "$STAGE/usr/lib/muse-board" \
           "$STAGE/usr/bin" \
           "$STAGE/usr/share/applications" \
           "$STAGE/usr/share/doc/muse-board" \
           "$STAGE/DEBIAN"

cp "$APP/run.py" "$STAGE/usr/lib/muse-board/"
cp -r "$APP/muse" "$APP/frontend" "$STAGE/usr/lib/muse-board/"
# run.py looks for its window icon beside itself, so it travels with the app
# as well as going into the icon theme further down.
cp "$APP/muse.png" "$STAGE/usr/lib/muse-board/"
find "$STAGE/usr/lib/muse-board" -name '__pycache__' -type d -prune -exec rm -rf {} +
find "$STAGE/usr/lib/muse-board" -name '*.py[co]' -delete

# Tells store.py that boards belong in Documents, not next to the app. /usr/lib
# is nobody's board folder, and it is writable when the app is run as root.
touch "$STAGE/usr/lib/muse-board/.system-install"

install -m 755 "$HERE/muse.launcher" "$STAGE/usr/bin/muse-board"

# --- 2/4 vendor the pip-only dependencies -----------------------------------

say "2/4  vendoring dependencies"
# pystray is left out on purpose: only quick capture imports it, and that is
# Windows-only. websockets is pinned in requirements.txt and matters here, see
# the note in muse.launcher.
grep -v '^\s*#' "$APP/requirements.txt" | grep -v '^\s*$' | grep -v '^pystray' \
    > "$STAGE/requirements.deb.txt"
"$PYTHON" -m pip install --quiet --no-compile --target "$STAGE/usr/lib/muse-board/vendor" \
    -r "$STAGE/requirements.deb.txt"
rm -f "$STAGE/requirements.deb.txt"
find "$STAGE/usr/lib/muse-board/vendor" -name '__pycache__' -type d -prune -exec rm -rf {} +
find "$STAGE/usr/lib/muse-board/vendor" -name '*.py[co]' -delete
rm -rf "$STAGE/usr/lib/muse-board/vendor/bin"

# --- 3/4 desktop entry, icons, licence, control -----------------------------

say "3/4  desktop entry, icons, control"
sed -e 's|^Exec=.*|Exec=muse-board|' \
    -e 's|^Icon=.*|Icon=muse-board|' \
    -e '/^# Template\./d' \
    -e '/^# which writes the resolved copy/d' \
    "$APP/packaging/muse.desktop" > "$STAGE/usr/share/applications/muse-board.desktop"
chmod 644 "$STAGE/usr/share/applications/muse-board.desktop"

"$PYTHON" - "$APP/muse.png" "$STAGE" <<'PY'
import sys, pathlib
from PIL import Image
src, stage = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
icon = Image.open(src).convert("RGBA")
for size in (512, 256, 128, 64, 48, 32):
    out = stage / f"usr/share/icons/hicolor/{size}x{size}/apps"
    out.mkdir(parents=True, exist_ok=True)
    resized = icon if icon.size == (size, size) else icon.resize((size, size), Image.LANCZOS)
    resized.save(out / "muse-board.png")
print(f"   icons: 512 256 128 64 48 32")
PY
find "$STAGE/usr/share/icons" -name '*.png' -exec chmod 644 {} +

{
    echo "Muse"
    echo
    cat "$APP/packaging/EULA.txt"
} > "$STAGE/usr/share/doc/muse-board/copyright"
chmod 644 "$STAGE/usr/share/doc/muse-board/copyright"

INSTALLED_KB="$(du -sk "$STAGE/usr" | cut -f1)"

cat > "$STAGE/DEBIAN/control" <<EOF
Package: muse-board
Version: $VERSION
Architecture: $ARCH
Maintainer: Martin De Lange <martin@martinworks.org>
Installed-Size: $INSTALLED_KB
Depends: python3 (>= $PYVER), python3 (<< $PYNEXT), python3-gi, gir1.2-gtk-3.0, gir1.2-webkit2-4.1
Recommends: xdg-utils, fonts-dejavu-core
Suggests: wl-clipboard, xclip
Section: graphics
Priority: optional
Homepage: https://martinworks.org
Description: Local visual board for notes, images and files
 Muse is a visual board that keeps everything on your own machine. Notes,
 to-dos, code, images, links, PDFs and live files sit on a canvas you arrange
 yourself, in folders you can read without the app.
 .
 Boards are plain folders and JSON, not a database, so nothing is locked in.
 The window is WebKitGTK; the server it talks to only ever listens on
 localhost.
EOF

cat > "$STAGE/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
    # Without these the menu entry can take a login to appear, and the icon
    # stays generic until the cache catches up.
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database -q /usr/share/applications || true
    fi
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -q -f -t /usr/share/icons/hicolor || true
    fi
fi
exit 0
EOF
chmod 755 "$STAGE/DEBIAN/postinst"

cat > "$STAGE/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database -q /usr/share/applications || true
    fi
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -q -f -t /usr/share/icons/hicolor || true
    fi
fi
exit 0
EOF
chmod 755 "$STAGE/DEBIAN/postrm"

# Boards live in the user's Documents, never under /usr, so nothing the package
# owns is user data and removal takes nothing with it.

# --- 4/4 build --------------------------------------------------------------

say "4/4  dpkg-deb"
mkdir -p "$OUT"
rm -f "$OUT/$PKG"
dpkg-deb --root-owner-group --build "$STAGE" "$OUT/$PKG" >/dev/null

echo
echo "Done. Package: $OUT/$PKG"
echo "Install with:  sudo apt install '$OUT/$PKG'"
echo "Remove with:   sudo apt remove muse-board"
