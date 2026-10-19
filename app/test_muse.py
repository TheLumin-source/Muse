"""Muse test suite.

Self-contained: no pytest, no running server, no network. It points Muse at a
throwaway data folder, drives the API in-process with FastAPI's TestClient, and
checks the flows that matter - the ones that would quietly break on an update.

    python test_muse.py

Exits non-zero if anything fails, so it can gate a release.
"""

from __future__ import annotations

import io
import os
import sys
import tempfile
import traceback
from pathlib import Path

# Point every path (Projects, Backups, Exports, thumbnail cache) at a temp dir
# BEFORE importing the app, since those roots are resolved at import time.
_TMP = Path(tempfile.mkdtemp(prefix="muse-test-"))
os.environ["MUSE_DATA"] = str(_TMP)

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient          # noqa: E402
from PIL import Image                              # noqa: E402

from muse.app import app                           # noqa: E402

client = TestClient(app)

_tests: list = []


def test(fn):
    _tests.append(fn)
    return fn


def eq(a, b, msg=""):
    if a != b:
        raise AssertionError(f"{msg}: expected {b!r}, got {a!r}")


def ok(cond, msg=""):
    if not cond:
        raise AssertionError(msg or "expected truthy")


def png_bytes(w=120, h=90, color=(200, 120, 80)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, "PNG")
    return buf.getvalue()


def pdf_bytes() -> bytes:
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "test pdf", fontsize=20)
    data = doc.tobytes()
    doc.close()
    return data


def current_project() -> str:
    return client.get("/api/projects").json()["current"]


def home_board(pid: str) -> str:
    return client.get(f"/api/p/{pid}/tree").json()["home"]


# --- tests -----------------------------------------------------------------


@test
def first_run_seeds_a_project():
    data = client.get("/api/projects").json()
    ok(data["current"], "a current project exists on first run")
    ok(any(p["name"] == "My first project" for p in data["projects"]),
       "welcome project is created")


@test
def board_saves_and_reloads_elements():
    pid = current_project()
    board = client.post(f"/api/p/{pid}/boards", json={"title": "T"}).json()
    bid = board["id"]
    full = client.get(f"/api/p/{pid}/boards/{bid}").json()["board"]
    full["elements"] = [{"id": "e1", "type": "note", "x": 10, "y": 20,
                         "w": 200, "h": 150, "color": "#abcdef",
                         "title": "Hi", "text": "keyword zebra"}]
    r = client.put(f"/api/p/{pid}/boards/{bid}", json=full)
    eq(r.status_code, 200, "PUT board")
    again = client.get(f"/api/p/{pid}/boards/{bid}").json()["board"]
    eq(len(again["elements"]), 1, "element count survives reload")
    eq(again["elements"][0]["color"], "#abcdef", "custom colour survives")


@test
def upload_image_reports_dimensions():
    pid = current_project()
    bid = home_board(pid)
    r = client.post(f"/api/p/{pid}/boards/{bid}/assets",
                    files={"file": ("pic.png", png_bytes(), "image/png")})
    info = r.json()
    eq(info["kind"], "image", "image kind")
    eq(info["nw"], 120, "natural width")
    ok(client.get(f"/media/{pid}/{bid}/{info['src']}").status_code == 200, "asset served")


@test
def upload_pdf_makes_a_thumbnail():
    pid = current_project()
    bid = home_board(pid)
    r = client.post(f"/api/p/{pid}/boards/{bid}/assets",
                    files={"file": ("doc.pdf", pdf_bytes(), "application/pdf")})
    info = r.json()
    eq(info["kind"], "pdf", "pdf kind")
    ok(info.get("thumb"), "pdf thumbnail produced")
    ok(client.get(f"/media/{pid}/{bid}/{info['thumb']}").status_code == 200, "thumb served")


@test
def templates_list_and_instantiate():
    templates = client.get("/api/templates").json()["templates"]
    ok(len(templates) >= 20, "templates available")
    pid = current_project()
    made = client.post(f"/api/p/{pid}/boards/from-template",
                       json={"template": "game-flow"}).json()
    ok(len(made["elements"]) > 0, "template board has cards")
    ok(len(made["connectors"]) > 0, "flow template has connectors")


@test
def search_finds_content():
    pid = current_project()
    hits = client.get(f"/api/p/{pid}/search", params={"q": "zebra"}).json()["hits"]
    ok(any(h.get("kind") == "note" for h in hits), "search finds the note text")


@test
def trash_and_restore_a_board():
    pid = current_project()
    b = client.post(f"/api/p/{pid}/boards", json={"title": "Doomed"}).json()
    bid = b["id"]
    client.delete(f"/api/p/{pid}/boards/{bid}")
    trash = client.get(f"/api/p/{pid}/trash").json()["boards"]
    ok(any(t["id"] == bid for t in trash), "deleted board is in the trash")
    client.post(f"/api/p/{pid}/trash/{bid}/restore")
    ok(client.get(f"/api/p/{pid}/boards/{bid}").status_code == 200, "board restored")


@test
def highlight_returns_spans():
    r = client.post("/api/highlight", json={"code": "print(1)", "lang": "python", "dark": True})
    ok("<span" in r.json()["html"], "code is highlighted")


@test
def export_pdf_png_html():
    pid = current_project()
    bid = home_board(pid)
    for fmt in ("pdf", "png", "html"):
        r = client.post(f"/api/p/{pid}/boards/{bid}/export", json={"format": fmt}).json()
        ok(Path(r["path"]).exists(), f"{fmt} export file exists")


@test
def update_check_is_well_formed():
    data = client.get("/api/update/check").json()
    for key in ("current", "available", "latest"):
        ok(key in data, f"update check has {key}")


@test
def backup_creates_a_zip():
    import zipfile
    r = client.post("/api/backups/now").json()
    path = Path(r["path"])
    ok(path.exists(), "backup file written")
    names = zipfile.ZipFile(path).namelist()
    ok(any(n.endswith("project.json") for n in names), "backup contains projects")
    ok(zipfile.ZipFile(path).testzip() is None, "backup zip is intact")


# --- runner ----------------------------------------------------------------


def main() -> int:
    passed, failed = 0, 0
    for fn in _tests:
        try:
            fn()
            passed += 1
            print(f"  ok   {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  FAIL {fn.__name__}: {exc}")
            if os.environ.get("MUSE_TEST_VERBOSE"):
                traceback.print_exc()
    print(f"\n{passed} passed, {failed} failed")
    import shutil
    shutil.rmtree(_TMP, ignore_errors=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
