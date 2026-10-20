# Muse

A local visual board. Drop notes, images, links, PDFs, files, to-do lists and
code onto an endless canvas and arrange them until the idea makes sense.

Everything stays on your machine. No account, no cloud, no telemetry. The server
binds to `127.0.0.1` and nothing else, and your boards are plain folders and
JSON files you can read, copy and back up without Muse installed.

Runs on **Linux** (WebKitGTK) and **Windows** (WebView2).

---

## Install on Linux

Muse ships as a Debian package for Debian, Ubuntu and Mint. It is not in any
archive, so you build it once and install the result.

### Build the package

```bash
sudo apt install python3-venv python3-pip python3-gi gir1.2-gtk-3.0 gir1.2-webkit2-4.1
```

```bash
git clone https://github.com/TheLumin-source/Muse.git && cd Muse
```

```bash
app/packaging/linux/build-deb.sh
```

That writes `out/muse-board_<version>_amd64.deb`. Install it:

```bash
sudo apt install ./out/muse-board_1.0.0_amd64.deb
```

Then launch it from your application menu, or from a terminal:

```bash
muse-board
```

**The package is named `muse-board`, not `muse`.** Ubuntu already ships a
package and a binary called `muse`, the MusE audio sequencer, and sharing the
name lets an ordinary `apt upgrade` replace this app with that one.

**The package is tied to the Python it was built against.** The bundled
dependencies include compiled wheels, so a package built on Python 3.12 declares
`python3 (>= 3.12), python3 (<< 3.13)` and apt will refuse to install it
elsewhere rather than half-install it. Build it on the oldest distribution you
intend to support.

### Or run it from source, without installing

```bash
python3 -m venv --system-site-packages app/.venv
```

```bash
app/.venv/bin/pip install -r app/requirements.txt
```

```bash
app/muse.sh
```

`--system-site-packages` is required, not a convenience: pywebview renders
through the distribution's PyGObject and WebKitGTK, which pip cannot install.

To add it to your application menu without packaging:

```bash
app/muse.sh --install-desktop
```

### Nvidia

If the window opens blank or garbled, that is WebKitGTK 2.42 and newer using a
DMA-BUF path the Nvidia proprietary driver does not support. Both launchers
detect that driver and disable it automatically. If it persists:

```bash
WEBKIT_DISABLE_COMPOSITING_MODE=1 muse-board
```

This path is untested on real Nvidia hardware. Please open an issue if it fails.

---

## Install on Windows

### From source

Install Python 3.10 or newer, then:

```bat
py -m pip install -r app\requirements.txt
```

Double click `app\Muse.bat`. It finds your Python automatically; set
`MUSE_PYTHON` to point at a specific interpreter if you have several.

### Build an installer

`app\packaging\build.ps1` freezes the app with PyInstaller and, if
[Inno Setup](https://jrsoftware.org/isdl.php) is installed, wraps it into
`out\Muse Setup.exe`:

```bat
powershell -ExecutionPolicy Bypass -File app\packaging\build.ps1
```

Without Inno Setup it stops after the freeze, leaving a runnable
`app\dist\Muse\Muse.exe`.

---

## Running it

| | |
|---|---|
| `muse-board` | desktop window |
| `muse-board --browser` | open in your default browser instead |
| `muse-board --serve` | server only, no window |
| `muse-board --port 9000` | use a different port, default 8810 |

From source, substitute `app/muse.sh` on Linux or `app\Muse.bat` on Windows.

Never run it with `sudo`. Your boards would be created owned by root.

---

## Where your work lives

| Installed from | Boards go to |
|---|---|
| the Debian package | `~/Documents/Muse` |
| the Windows installer | `Documents\Muse` |
| a source checkout | the folder containing `app/` |

Set `MUSE_DATA` to put them anywhere you like:

```bash
MUSE_DATA=/path/of/your/choosing muse-board
```

A project is a folder, a board is a folder inside it, and a board is one JSON
file plus its images. Copy the folder and you have copied the work. Muse keeps
the previous save as `board.bak.json` beside every board, and zips a backup on
launch when the newest one is more than a day old.

Removing the package leaves all of it untouched.

---

## Requirements

**Linux:** Python 3.10 or newer, GTK 3, WebKitGTK 4.1 and PyGObject from your
distribution. Optional and degrading quietly to nothing when absent:
`xdg-utils` to reveal files in your file manager, `wl-clipboard` or `xclip` to
copy files to the clipboard, `fontconfig` for PDF and image export.

**Windows:** Python 3.10 or newer and the WebView2 runtime, which Windows 11 and
up to date Windows 10 already have.

---

## Development

Tests are self contained, need no pytest and no running server, and gate a
release:

```bash
app/.venv/bin/python app/test_muse.py
```

The frontend is vanilla JavaScript ES modules and plain CSS with no build step
and no framework, so an edit to `app/frontend` is live on the next launch. The
backend is FastAPI and uvicorn. The version lives in exactly one place,
`app/muse/__init__.py`.

`app/README.md` is the user manual and `app/DESIGN.md` explains why the thing is
built the way it is.

---

## Licence

[PolyForm Noncommercial License 1.0.0](LICENSE). Use it, change it and share it
for any noncommercial purpose: personal work, hobby projects, study, charities,
schools, public research and government all count explicitly.

Selling it, or using it commercially, is not granted here and needs a separate
agreement. This makes Muse source available rather than open source in the OSI
sense, since that definition requires permitting commercial use.

`app/packaging/EULA.txt` is a separate document that applies only to prebuilt
installers distributed from martinworks.org.
