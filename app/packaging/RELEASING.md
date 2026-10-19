# Releasing Muse

How to cut a new version.

> Stale, needs a decision: everything below about uploading to the shop, buyers
> and the auto-updater was written when Muse was for sale. If that is no longer
> the plan, sections 3 and "What buyers see" should go, and `UPDATE_URL` in
> `muse/__init__.py` with them. Left in place rather than deleted on an
> assumption.

## 1. Bump the version in ONE place

Edit `muse/__init__.py`:

    __version__ = "1.1.0"

That is the single source of truth. `build.ps1` reads it and stamps the installer
with it automatically, and the running app reports it to the auto-updater. You do
not touch the installer script. Versions are compared as numbers (1.10 beats 1.9).

## 2. Build the installer

```
powershell -ExecutionPolicy Bypass -File D:\Muse\app\packaging\build.ps1
```

This freezes the app with PyInstaller and, if Inno Setup is installed, wraps it
into `D:\Muse\out\Muse Setup.exe`. If Inno Setup is missing, install it once
(free) from https://jrsoftware.org/isdl.php and re-run.

## 2b. Build the Linux package

```
app/packaging/linux/build-deb.sh
```

Produces `out/muse_<version>_amd64.deb`. There is no PyInstaller step: the
window is WebKitGTK reached through the distro's PyGObject, and neither freezes
usefully, so the package ships the source, declares those as dependencies, and
vendors everything pip-only into `/usr/lib/muse/vendor`. Installing needs no
network and no pip.

Two things to know before building:

- The vendored wheels are compiled for whichever Python runs the script, and
  the package declares that exact python3 version. Build it on the oldest
  distro you mean to support, or it will refuse to install on the others.
  `MUSE_BUILD_PYTHON=/path/to/python` picks the interpreter.
- Boards go to Documents, not next to the app. The package drops a
  `.system-install` marker in `/usr/lib/muse` and `store.py` reads it, because
  `/usr/lib` is nobody's board folder and it is writable when the app runs as
  root.

Install and remove:

```
sudo apt install ./out/muse_<version>_amd64.deb
sudo apt remove muse
```

Removal leaves Documents/Muse alone; the package owns nothing under it.

## 3. Upload to your shop

Put two files on your site:

1. `Muse Setup.exe` (rename per version if you like, e.g. Muse-1.1.0-Setup.exe).
2. `latest.json`, the manifest Muse checks. It must live at the URL set in
   `muse/__init__.py` (`UPDATE_URL`, currently
   `https://martinworks.org/muse/latest.json`):

```json
{
  "version": "1.1.0",
  "url": "https://martinworks.org/muse/Muse-1.1.0-Setup.exe",
  "notes": "What's new in this version, in one short line.",
  "date": "2026-08-01"
}
```

## What buyers see

On the next launch after you publish, Muse quietly checks `latest.json`. If the
version there is newer than theirs, a small "Muse x.y is available" bar appears
with an **Update now** button. Clicking it downloads the new installer, closes
Muse, installs silently, and reopens. Nothing installs without that click.

Because the installer is per-user and fetched by the app itself, there is no UAC
prompt and no SmartScreen "unknown publisher" warning during the auto-update.
(A brand-new buyer running the very first download from a browser may still see
SmartScreen until the installer builds reputation, or until you code-sign it.)

## Optional: code signing

Buyers get the smoothest first run if `Muse Setup.exe` and `Muse.exe` are signed
with an Authenticode certificate. It is not required, but it removes the initial
SmartScreen prompt. Sign the exe inside `dist\Muse` before building the installer,
and sign the finished `Muse Setup.exe` too.
