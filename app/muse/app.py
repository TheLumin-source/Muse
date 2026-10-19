"""FastAPI app: projects, boards, assets, link previews, search.

Every board route is scoped to a project: /api/p/{project_id}/...
"""

from __future__ import annotations

import io
import os
import re
import subprocess
import sys
from pathlib import Path

from fastapi import Body, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image

from . import (backup, capture, code, export, links, livefiles, render, store,
               templates, updater)

# When frozen, data files are unpacked under sys._MEIPASS; from source they sit
# beside the package.
_BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
FRONTEND = _BASE / "frontend"

app = FastAPI(title="Muse")


@app.middleware("http")
async def no_cache_frontend(request, call_next):
    """Never let the WebView run a stale copy of the app's own JS/CSS after an
    update. no-store means it is not written to cache at all. Assets and media
    (images, thumbnails) keep normal caching."""
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.endswith((".js", ".css", ".html")):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


# --- cache-busting -----------------------------------------------------------
#
# The definitive fix for the WebView serving stale code: stamp a content-based
# token onto every frontend URL. index.html carries the token on its <script>
# and <link> refs, and each served .js has its relative imports rewritten to
# carry it too, so the WHOLE module graph uses tokened URLs. Change any file and
# the token changes -> every URL changes -> the cache is forced to refetch.
# Change nothing and the URLs are stable -> caching still works.

# A relative module import: `from './x.js'`, `import './x.js'`, `import('./x.js')`.
_IMPORT_RE = re.compile(r"""(\bfrom\s+|\bimport\s*\(\s*|\bimport\s+)(['"])(\.{1,2}/[^'"]+?)(['"])""")
_REF_RE = re.compile(r'(\b(?:src|href)=")(/[^"?]+\.(?:js|css))(")')


def build_token() -> str:
    """Hex of the newest frontend file's mtime; changes on any edit or rebuild."""
    try:
        newest = max(p.stat().st_mtime_ns for p in FRONTEND.rglob("*") if p.is_file())
        return format(newest & 0xFFFFFFFFFF, "x")
    except Exception:
        return "0"


@app.get("/")
def index():
    token = build_token()
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    html = _REF_RE.sub(rf'\1\2?v={token}\3', html)
    return Response(html, media_type="text/html")


@app.get("/js/{name:path}")
def serve_module(name: str):
    """Serve a frontend ES module with its relative imports tokened for cache
    busting. This route sits above the StaticFiles mount so it wins."""
    if ".." in name or name.startswith("/"):
        raise HTTPException(400, "bad path")
    path = (FRONTEND / "js" / name).resolve()
    if not str(path).startswith(str((FRONTEND / "js").resolve())) or not path.exists():
        raise HTTPException(404, "no such module")
    token = build_token()
    text = path.read_text(encoding="utf-8")
    text = _IMPORT_RE.sub(rf'\1\2\3?v={token}\4', text)
    return Response(text, media_type="application/javascript")


@app.get("/api/version")
def version():
    """Version plus a build stamp derived from the frontend's newest file, so it
    changes every time the code is updated - a way to confirm a fresh load."""
    from datetime import datetime
    from . import __version__
    try:
        newest = max(p.stat().st_mtime for p in FRONTEND.rglob("*") if p.is_file())
        build = datetime.fromtimestamp(newest).strftime("%b-%d %H:%M")
    except Exception:
        build = "?"
    return {"version": __version__, "build": build}


# --- auto update -------------------------------------------------------------


@app.get("/api/update/check")
def update_check():
    return updater.check()


@app.post("/api/update/apply")
def update_apply(payload: dict = Body(...)):
    url = (payload.get("url") or "").strip()
    if not url.lower().startswith("https://"):
        raise HTTPException(400, "bad update url")
    try:
        setup = updater.download(url)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"download failed: {exc}")
    updater.apply_and_restart(setup)
    return {"ok": True}


# --- projects --------------------------------------------------------------


@app.get("/api/projects")
def get_projects():
    current = store.ensure_project()
    settings = store.read_settings()
    return {
        "projects": store.all_projects(),
        "current": current["id"],
        "last_board": settings.get("board"),
        "root": str(store.PROJECTS_DIR),
    }


@app.get("/api/templates")
def get_templates():
    return {"templates": templates.catalogue()}


@app.post("/api/projects")
def post_project(payload: dict = Body(default={})):
    return store.create_project(payload.get("name") or "New project",
                                template=payload.get("template"))


@app.patch("/api/projects/{project_id}")
def patch_project(project_id: str, payload: dict = Body(...)):
    if "name" in payload:
        return store.rename_project(project_id, payload["name"])
    if "home" in payload:
        project = store.load_project(project_id)
        if not project:
            raise HTTPException(404, "no such project")
        project["home"] = payload["home"]
        return store.save_project(project)
    return {"ok": True}


@app.delete("/api/projects/{project_id}")
def remove_project(project_id: str):
    if not store.load_project(project_id):
        raise HTTPException(404, "no such project")
    store.delete_project(project_id)
    return {"ok": True, "remaining": len(store.all_projects())}


@app.post("/api/projects/{project_id}/open")
def open_project(project_id: str):
    """Remember this as the project to reopen next time."""
    if not store.load_project(project_id):
        raise HTTPException(404, "no such project")
    store.touch_project(project_id)
    store.write_settings(project=project_id)
    return {"home": store.home_board(project_id)["id"]}


@app.post("/api/projects/{project_id}/reveal")
def reveal_project(project_id: str):
    """Show the project's folder in the file manager."""
    path = store.project_dir(project_id)
    livefiles.reveal_path(str(path))
    return {"path": str(path)}


# --- boards ----------------------------------------------------------------


@app.get("/api/p/{project_id}/tree")
def get_tree(project_id: str):
    if not store.load_project(project_id):
        raise HTTPException(404, "no such project")
    return {"tree": store.board_tree(project_id),
            "home": store.home_board(project_id)["id"]}


@app.post("/api/p/{project_id}/boards")
def post_board(project_id: str, payload: dict = Body(default={})):
    return store.create_board(project_id, payload.get("title") or "Untitled board",
                              payload.get("parent_id"))


@app.post("/api/p/{project_id}/boards/from-template")
def post_board_from_template(project_id: str, payload: dict = Body(...)):
    spec = templates.build(payload.get("template") or "")
    if not spec:
        raise HTTPException(404, "no such template")
    if payload.get("title"):
        spec["title"] = payload["title"]
    return store.create_from_spec(project_id, spec, payload.get("parent_id"))


@app.get("/api/p/{project_id}/boards/{board_id}")
def get_board(project_id: str, board_id: str):
    board = store.load_board(project_id, board_id)
    if not board:
        raise HTTPException(404, "no such board")
    store.write_settings(project=project_id, board=board_id)
    return {"board": board, "trail": store.breadcrumbs(project_id, board_id)}


def _store_board(project_id: str, board_id: str, incoming: dict) -> dict:
    existing = store.load_board(project_id, board_id)
    if not existing:
        raise HTTPException(404, "no such board")
    # Only the client-owned fields; never let a stray payload rewrite lineage.
    existing.update({
        "title": incoming.get("title", existing["title"]),
        "view": incoming.get("view", existing["view"]),
        "elements": incoming.get("elements", []),
        "connectors": incoming.get("connectors", []),
    })
    return store.save_board(project_id, existing)


@app.put("/api/p/{project_id}/boards/{board_id}")
def put_board(project_id: str, board_id: str, board: dict = Body(...)):
    if board.get("id") != board_id:
        raise HTTPException(400, "board id mismatch")
    return {"modified": _store_board(project_id, board_id, board)["modified"]}


@app.post("/api/p/{project_id}/boards/{board_id}/beacon")
async def beacon_board(project_id: str, board_id: str, request: Request):
    """Last-gasp save from sendBeacon as the window closes."""
    try:
        board = await request.json()
    except Exception:
        raise HTTPException(400, "bad payload")
    if board.get("id") != board_id:
        raise HTTPException(400, "board id mismatch")
    _store_board(project_id, board_id, board)
    return {"ok": True}


@app.patch("/api/p/{project_id}/boards/{board_id}")
def patch_board(project_id: str, board_id: str, payload: dict = Body(...)):
    board = store.load_board(project_id, board_id)
    if not board:
        raise HTTPException(404, "no such board")
    if "title" in payload:
        board["title"] = payload["title"] or "Untitled board"
    if "parent_id" in payload:
        board["parent_id"] = payload["parent_id"]
    if "icon" in payload:
        board["icon"] = payload["icon"]
    store.save_board(project_id, board)
    return {"ok": True}


@app.delete("/api/p/{project_id}/boards/{board_id}")
def remove_board(project_id: str, board_id: str):
    if not store.load_board(project_id, board_id):
        raise HTTPException(404, "no such board")
    store.delete_board(project_id, board_id)
    return {"ok": True}


@app.post("/api/p/{project_id}/boards/{board_id}/receive")
def receive_elements(project_id: str, board_id: str, payload: dict = Body(...)):
    """Take cards from another board, bringing their images and files along."""
    board = store.load_board(project_id, board_id)
    if not board:
        raise HTTPException(404, "no such board")
    source_board = payload.get("from")
    elements = payload.get("elements") or []

    for element in elements:
        for field in ("src", "thumb"):
            if element.get(field) and source_board and source_board != board_id:
                try:
                    element[field] = store.copy_asset(
                        project_id, source_board, board_id, element[field])
                except (OSError, ValueError):
                    element[field] = "" if field == "src" else None
        element["parent"] = None
    board["elements"].extend(elements)
    board["connectors"].extend(payload.get("connectors") or [])
    store.save_board(project_id, board)
    return {"ok": True, "count": len(elements)}


@app.get("/api/p/{project_id}/boards/{board_id}/preview")
def board_preview(project_id: str, board_id: str):
    return {"elements": store.board_preview(project_id, board_id)}


# --- trash -----------------------------------------------------------------


@app.get("/api/p/{project_id}/trash")
def get_trash(project_id: str):
    return {"boards": store.list_trash(project_id)}


@app.post("/api/p/{project_id}/trash/{board_id}/restore")
def restore_from_trash(project_id: str, board_id: str):
    board = store.restore_board(project_id, board_id)
    if not board:
        raise HTTPException(404, "not in the trash")
    return board


@app.delete("/api/p/{project_id}/trash/{board_id}")
def purge_from_trash(project_id: str, board_id: str):
    store.purge_board(project_id, board_id)
    return {"ok": True}


@app.delete("/api/p/{project_id}/trash")
def empty_the_trash(project_id: str):
    store.empty_trash(project_id)
    return {"ok": True}


# --- assets ----------------------------------------------------------------


@app.post("/api/p/{project_id}/boards/{board_id}/assets")
async def upload_asset(project_id: str, board_id: str, file: UploadFile = File(...)):
    if not store.load_board(project_id, board_id):
        raise HTTPException(404, "no such board")
    data = await file.read()
    src = store.save_asset(project_id, board_id, file.filename or "file", data)
    info = {
        "src": src,
        "name": file.filename or "file",
        "size": len(data),
        "ext": os.path.splitext(file.filename or "")[1].lstrip(".").lower(),
        "kind": "file",
    }
    try:
        with Image.open(io.BytesIO(data)) as img:
            info.update(kind="image", nw=img.width, nh=img.height)
        return info
    except Exception:
        pass  # not an image; maybe a PDF, otherwise a plain file

    if info["ext"] == "pdf":
        try:
            asset_abs = store.asset_path(project_id, board_id, src)
            thumb = livefiles.thumbnail(str(asset_abs), 480)
            if thumb:
                info["thumb"] = store.save_asset(
                    project_id, board_id, "pdf_thumb.jpg", thumb.read_bytes())
                info["kind"] = "pdf"
        except Exception:
            pass  # still a usable file card without the preview
    return info


@app.get("/media/{project_id}/{board_id}/{rel:path}")
def media(project_id: str, board_id: str, rel: str):
    try:
        path = store.asset_path(project_id, board_id, rel)
    except ValueError:
        raise HTTPException(400, "bad path")
    if not path.exists():
        raise HTTPException(404, "no such asset")
    return FileResponse(path)


@app.post("/api/open")
def open_asset(payload: dict = Body(...)):
    """Hand a dropped file to whatever Windows uses for it."""
    try:
        path = store.asset_path(payload["project_id"], payload["board_id"], payload["src"])
    except (ValueError, KeyError):
        raise HTTPException(400, "bad path")
    if not path.exists():
        raise HTTPException(404, "no such asset")
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606 - a local file the user just dropped in
    else:
        subprocess.Popen(["xdg-open", str(path)])
    return {"ok": True}


# --- extras ----------------------------------------------------------------


@app.post("/api/link-preview")
def link_preview(payload: dict = Body(...)):
    url = (payload.get("url") or "").strip()
    if not url:
        raise HTTPException(400, "no url")
    return links.fetch_preview(url, payload.get("project_id"), payload.get("board_id"))


@app.get("/api/p/{project_id}/search")
def search(project_id: str, q: str = ""):
    return {"hits": store.search(project_id, q)}


@app.post("/api/p/{project_id}/boards/{board_id}/export")
def export_html(project_id: str, board_id: str, payload: dict = Body(default={})):
    """Export a board. format: 'html' (default), 'pdf', or 'png'. Reveals it."""
    fmt = (payload.get("format") or "html").lower()
    if fmt in ("pdf", "png"):
        out = render.render_board(project_id, board_id)
        path = out[fmt]
    else:
        path = str(export.export_board(project_id, board_id))
    livefiles.reveal_path(path)
    return {"path": path, "name": Path(path).name, "format": fmt}


# --- code cards ---------------------------------------------------------------


@app.post("/api/highlight")
def post_highlight(payload: dict = Body(...)):
    return code.highlight(payload.get("code") or "",
                          payload.get("lang") or "auto",
                          bool(payload.get("dark", True)))


@app.get("/api/languages")
def get_languages():
    return {"languages": code.languages()}


@app.get("/highlight.css")
def highlight_css():
    css = f"{code.stylesheet(True)}\n\n{code.stylesheet(False)}"
    return Response(css, media_type="text/css")


# --- quick capture -----------------------------------------------------------


@app.get("/api/captures")
def get_captures():
    return {"captures": capture.pending(), "status": capture.state}


@app.post("/api/captures/{name}/claim")
def claim_capture(name: str, payload: dict = Body(...)):
    project_id = payload.get("project_id") or ""
    board_id = payload.get("board_id") or ""
    if not store.load_board(project_id, board_id):
        raise HTTPException(404, "no such board")
    info = capture.claim(name, project_id, board_id)
    if not info:
        raise HTTPException(404, "already claimed")
    return info


# --- live files on this machine --------------------------------------------


@app.post("/api/fs/pick")
def fs_pick(payload: dict = Body(default={})):
    """Open a real file dialog and hand back real paths."""
    paths = livefiles.pick(payload.get("mode") or "file")
    return {"paths": paths, "items": [livefiles.describe(p) for p in paths]}


@app.get("/api/fs/info")
def fs_info(path: str):
    return livefiles.describe(path)


@app.get("/api/fs/list")
def fs_list(path: str, kinds: str = "all", limit: int = 24):
    return livefiles.listing(path, kinds, limit)


@app.get("/api/fs/thumb")
def fs_thumb(path: str, size: int = 320, v: str = ""):
    thumb = livefiles.thumbnail(path, size)
    if not thumb:
        raise HTTPException(404, "no thumbnail")
    return FileResponse(thumb, headers={"Cache-Control": "no-cache"})


@app.post("/api/fs/open")
def fs_open(payload: dict = Body(...)):
    if not livefiles.open_path(payload.get("path") or ""):
        raise HTTPException(404, "no such file")
    return {"ok": True}


@app.post("/api/fs/reveal")
def fs_reveal(payload: dict = Body(...)):
    if not livefiles.reveal_path(_resolve_target(payload)):
        raise HTTPException(404, "no such file")
    return {"ok": True}


def _resolve_target(payload: dict) -> str:
    """A target is either a real path (live cards) or a board asset (src)."""
    if payload.get("path"):
        return payload["path"]
    try:
        return str(store.asset_path(payload["project_id"], payload["board_id"], payload["src"]))
    except (KeyError, ValueError):
        return ""


@app.post("/api/clipboard/copy")
def clipboard_copy(payload: dict = Body(...)):
    if not livefiles.copy_to_clipboard(_resolve_target(payload)):
        raise HTTPException(404, "could not copy")
    return {"ok": True}


@app.post("/api/fs/save-copy")
def fs_save_copy(payload: dict = Body(...)):
    ok = livefiles.save_copy(_resolve_target(payload))
    return {"ok": ok}


# --- backups -----------------------------------------------------------------


@app.get("/api/backups")
def get_backups():
    return {"backups": backup.list_backups(), "folder": str(backup.BACKUP_DIR)}


@app.post("/api/backups/now")
def make_backup():
    path = backup.backup_now()
    if not path:
        raise HTTPException(400, "nothing to back up yet")
    return {"name": path.name, "path": str(path)}


@app.post("/api/backups/reveal")
def reveal_backups():
    backup.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    livefiles.reveal_path(str(backup.BACKUP_DIR))
    return {"ok": True, "folder": str(backup.BACKUP_DIR)}


@app.exception_handler(ValueError)
def value_error(request, exc):
    return JSONResponse({"detail": str(exc)}, status_code=400)


app.mount("/", StaticFiles(directory=FRONTEND), name="frontend")
