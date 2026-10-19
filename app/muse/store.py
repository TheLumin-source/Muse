"""Storage: projects are folders, boards are folders inside them, no database.

D:\\Muse\\
  settings.json                 last project and board opened
  Projects\\
    Studio rebrand\\             one folder per project, named as you named it
      project.json
      boards\\
        b_7f3a91\\
          board.json
          board.bak.json        the previous save, kept as a safety net
          assets\\
            shot_2c81.png
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import sys
from datetime import datetime
from pathlib import Path

from . import platform

APP_DIR = Path(__file__).resolve().parent.parent          # ...\Muse\app


def _data_root() -> Path:
    """Where boards live.

    Running from source (dev): beside the app, e.g. D:\\Muse.
    Installed (frozen exe): Documents\\Muse, because the install folder under
    Program Files is read-only and gets replaced on update.
    Installed from the Linux package: the same, for the same reason. That build
    is not frozen, so it leaves a marker beside the app rather than having the
    code guess from the path or from whether /usr/lib happens to be writable,
    which it is when someone runs the app as root.
    A MUSE_DATA env var overrides all of them, for anyone who wants their boards
    on a different drive.
    """
    override = os.environ.get("MUSE_DATA")
    if override:
        return Path(override)
    if getattr(sys, "frozen", False) or (APP_DIR / ".system-install").exists():
        return platform.documents_dir() / "Muse"
    return APP_DIR.parent


DATA_ROOT = _data_root()
PROJECTS_DIR = DATA_ROOT / "Projects"
SETTINGS_FILE = DATA_ROOT / "settings.json"

SAFE_ID = re.compile(r"^[a-z]_[0-9a-f]{8}$")
RESERVED = {"CON", "PRN", "AUX", "NUL", "COM1", "LPT1"}


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def new_id(prefix: str = "b") -> str:
    return f"{prefix}_{secrets.token_hex(4)}"


def _write_atomic(path: Path, data: str) -> None:
    """Temp file + replace, so an interrupted save can never leave half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(data, encoding="utf-8")
    os.replace(tmp, path)


# --- settings --------------------------------------------------------------


def read_settings() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def write_settings(**values) -> dict:
    settings = read_settings()
    settings.update(values)
    _write_atomic(SETTINGS_FILE, json.dumps(settings, indent=2))
    return settings


# --- projects --------------------------------------------------------------


def folder_name(name: str, exclude: Path | None = None) -> str:
    """A tidy Windows-safe folder name for a project, kept unique."""
    clean = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", name).strip(" .")
    clean = re.sub(r"\s+", " ", clean)[:60] or "Untitled project"
    if clean.upper() in RESERVED:
        clean = f"{clean} project"
    candidate = clean
    suffix = 2
    while (PROJECTS_DIR / candidate).exists() and (PROJECTS_DIR / candidate) != exclude:
        candidate = f"{clean} {suffix}"
        suffix += 1
    return candidate


def all_projects() -> list[dict]:
    """Every project on disk, most recently opened first."""
    if not PROJECTS_DIR.exists():
        return []
    found = []
    for entry in PROJECTS_DIR.iterdir():
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        try:
            data = json.loads((entry / "project.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        boards = entry / "boards"
        data["folder"] = entry.name
        data["path"] = str(entry)
        data["boards"] = len(list(boards.glob("*/board.json"))) if boards.exists() else 0
        found.append(data)
    found.sort(key=lambda p: p.get("opened") or p.get("modified", ""), reverse=True)
    return found


def load_project(project_id: str) -> dict | None:
    return next((p for p in all_projects() if p["id"] == project_id), None)


def project_dir(project_id: str) -> Path:
    project = load_project(project_id)
    if not project:
        raise ValueError(f"no such project: {project_id}")
    return PROJECTS_DIR / project["folder"]


def create_project(name: str = "New project", *, seed: bool = True,
                   template: str | None = None) -> dict:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    project = {
        "id": new_id("p"),
        "name": name.strip() or "New project",
        "created": now(),
        "modified": now(),
        "opened": now(),
        "home": None,
    }
    directory = PROJECTS_DIR / folder_name(project["name"])
    (directory / "boards").mkdir(parents=True, exist_ok=True)
    _write_atomic(directory / "project.json",
                  json.dumps(project, indent=2, ensure_ascii=False))
    if template:
        from . import templates as template_module
        spec = template_module.build(template)
        home = create_from_spec(project["id"], spec) if spec else create_board(project["id"], "My board")
    elif seed:
        home = _seed_welcome(project["id"])
    else:
        home = create_board(project["id"], "My board")
    project["home"] = home["id"]
    save_project(project)
    return {**project, "folder": directory.name, "path": str(directory), "boards": 1}


def save_project(project: dict) -> dict:
    directory = project_dir(project["id"])
    keep = ("id", "name", "created", "modified", "opened", "home")
    stored = {k: project[k] for k in keep if k in project}
    stored["modified"] = now()
    _write_atomic(directory / "project.json",
                  json.dumps(stored, indent=2, ensure_ascii=False))
    return stored


def rename_project(project_id: str, name: str) -> dict | None:
    project = load_project(project_id)
    if not project:
        raise ValueError("no such project")
    old_dir = PROJECTS_DIR / project["folder"]
    project["name"] = name.strip() or project["name"]
    save_project(project)
    # Keep the folder name in step with the project name where Windows allows it.
    wanted = folder_name(project["name"], exclude=old_dir)
    if wanted != old_dir.name:
        try:
            old_dir.rename(PROJECTS_DIR / wanted)
        except OSError:
            pass  # something has the folder open; project.json is still correct
    return load_project(project_id)


def delete_project(project_id: str) -> Path:
    """Projects go to D:\\Muse\\Trash rather than evaporating."""
    source = project_dir(project_id)
    trash = DATA_ROOT / "Trash"
    trash.mkdir(parents=True, exist_ok=True)
    destination = trash / f"{source.name} {datetime.now():%Y-%m-%d %H%M}"
    shutil.move(str(source), str(destination))
    return destination


def touch_project(project_id: str) -> None:
    project = load_project(project_id)
    if project:
        project["opened"] = now()
        save_project(project)


def ensure_project() -> dict:
    """First run, or every project deleted: there is always somewhere to work."""
    projects = all_projects()
    if projects:
        last = read_settings().get("project")
        return next((p for p in projects if p["id"] == last), projects[0])
    return create_project("My first project")


# --- boards ----------------------------------------------------------------


def boards_dir(project_id: str) -> Path:
    return project_dir(project_id) / "boards"


def board_dir(project_id: str, board_id: str) -> Path:
    if not SAFE_ID.match(board_id):
        raise ValueError(f"bad board id: {board_id!r}")
    return boards_dir(project_id) / board_id


def blank_board(title: str = "Untitled board", parent_id: str | None = None) -> dict:
    return {
        "id": new_id("b"),
        "title": title,
        "parent_id": parent_id,
        "icon": "",
        "created": now(),
        "modified": now(),
        "view": {"x": 0, "y": 0, "zoom": 1},
        "elements": [],
        "connectors": [],
    }


def create_board(project_id: str, title: str = "Untitled board",
                 parent_id: str | None = None, *, seed: bool = False) -> dict:
    board = blank_board(title, parent_id)
    if seed:
        board["elements"] = welcome_elements()
    save_board(project_id, board)
    return board


def create_from_spec(project_id: str, spec: dict, parent_id: str | None = None) -> dict:
    """Turn a template spec into real boards. Nested boards are made first so the
    board cards on the parent can point at them."""
    board = blank_board(spec.get("title") or "Untitled board", parent_id)
    save_board(project_id, board)
    children = [create_from_spec(project_id, child, board["id"])
                for child in spec.get("children", [])]

    keys: dict[str, str] = {}
    elements = []
    for raw in spec.get("elements", []):
        element = dict(raw)
        key = element.pop("key", None)
        element["id"] = new_id("e")
        if key:
            keys[key] = element["id"]
        elements.append(element)

    for element in elements:
        if "child" in element:
            index = element.pop("child")
            child = children[index] if index < len(children) else None
            element["board_id"] = child["id"] if child else None
        if "children" in element:
            element["children"] = [keys[k] for k in element["children"] if k in keys]
        if element.get("parent"):
            element["parent"] = keys.get(element["parent"])
        if element.get("items"):
            element["items"] = [{**item, "id": new_id("t")} for item in element["items"]]
        element.setdefault("parent", None)
        element.setdefault("color", "white")

    board["elements"] = elements
    board["connectors"] = [
        {"id": new_id("c"), "from": keys[w["from"]], "to": keys[w["to"]],
         "arrow": "end", "color": "slate"}
        for w in spec.get("connectors", [])
        if w["from"] in keys and w["to"] in keys
    ]
    save_board(project_id, board)
    return board


def load_board(project_id: str, board_id: str) -> dict | None:
    path = board_dir(project_id, board_id) / "board.json"
    if not path.exists():
        return None
    try:
        board = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        backup = path.with_name("board.bak.json")
        if not backup.exists():
            raise
        board = json.loads(backup.read_text(encoding="utf-8"))
    board.setdefault("elements", [])
    board.setdefault("connectors", [])
    board.setdefault("view", {"x": 0, "y": 0, "zoom": 1})
    return board


def save_board(project_id: str, board: dict) -> dict:
    board["modified"] = now()
    path = board_dir(project_id, board["id"]) / "board.json"
    if path.exists():
        try:
            shutil.copy2(path, path.with_name("board.bak.json"))
        except OSError:
            pass  # a backup is a bonus, never a reason to fail the save
    _write_atomic(path, json.dumps(board, indent=2, ensure_ascii=False))
    return board


def delete_board(project_id: str, board_id: str, group: str | None = None) -> None:
    """Move a board and everything nested beneath it into the project's trash."""
    group = group or board_id
    for child in children_of(project_id, board_id):
        delete_board(project_id, child["id"], group)

    board = load_board(project_id, board_id) or {}
    source = board_dir(project_id, board_id)
    if not source.exists():
        return
    destination = trash_dir(project_id) / board_id
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(destination, ignore_errors=True)
    shutil.move(str(source), str(destination))
    _write_atomic(destination / "trash.json", json.dumps({
        "id": board_id,
        "title": board.get("title", "Untitled"),
        "parent_id": board.get("parent_id"),
        "count": len(board.get("elements", [])),
        "group": group,
        "deleted": now(),
    }, indent=2, ensure_ascii=False))


def trash_dir(project_id: str) -> Path:
    return project_dir(project_id) / ".trash"


def list_trash(project_id: str) -> list[dict]:
    """One entry per deleted board, newest first, grouped by the delete that did it."""
    directory = trash_dir(project_id)
    if not directory.exists():
        return []
    entries = []
    for entry in directory.iterdir():
        try:
            entries.append(json.loads((entry / "trash.json").read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    entries.sort(key=lambda e: e["deleted"], reverse=True)
    # Only the board you actually deleted is offered; its children ride along.
    return [e for e in entries if e["group"] == e["id"]]


def restore_board(project_id: str, board_id: str) -> dict | None:
    """Put a deleted board back, along with everything that went with it."""
    directory = trash_dir(project_id)
    restored = None
    for entry in list(directory.iterdir()) if directory.exists() else []:
        try:
            meta = json.loads((entry / "trash.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if meta["group"] != board_id and meta["id"] != board_id:
            continue
        destination = boards_dir(project_id) / meta["id"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        (entry / "trash.json").unlink(missing_ok=True)
        shutil.move(str(entry), str(destination))
        board = load_board(project_id, meta["id"])
        if board and meta["id"] == board_id:
            # If its old parent is gone, put it back at the top rather than nowhere.
            if board.get("parent_id") and not (boards_dir(project_id) / board["parent_id"]).exists():
                board["parent_id"] = None
                save_board(project_id, board)
            restored = board
    return restored


def purge_board(project_id: str, board_id: str) -> None:
    """Delete for real, from the trash."""
    directory = trash_dir(project_id)
    if not directory.exists():
        return
    for entry in list(directory.iterdir()):
        try:
            meta = json.loads((entry / "trash.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if meta["group"] == board_id or meta["id"] == board_id:
            shutil.rmtree(entry, ignore_errors=True)


def empty_trash(project_id: str) -> None:
    shutil.rmtree(trash_dir(project_id), ignore_errors=True)


def all_boards(project_id: str) -> list[dict]:
    directory = boards_dir(project_id)
    if not directory.exists():
        return []
    out = []
    for entry in sorted(directory.iterdir()):
        if not entry.is_dir() or not SAFE_ID.match(entry.name):
            continue
        try:
            board = json.loads((entry / "board.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        out.append({
            "id": board["id"],
            "title": board.get("title", "Untitled"),
            "parent_id": board.get("parent_id"),
            "icon": board.get("icon", ""),
            "modified": board.get("modified", ""),
            "count": len(board.get("elements", [])),
        })
    return out


def children_of(project_id: str, parent_id: str | None) -> list[dict]:
    return [b for b in all_boards(project_id) if b.get("parent_id") == parent_id]


def board_tree(project_id: str) -> list[dict]:
    """Nest the flat summaries into a tree of root boards."""
    boards = {b["id"]: {**b, "children": []} for b in all_boards(project_id)}
    roots = []
    for board in boards.values():
        parent = boards.get(board["parent_id"]) if board["parent_id"] else None
        if parent:
            parent["children"].append(board)
        else:
            roots.append(board)
    for board in boards.values():
        board["children"].sort(key=lambda b: b["title"].lower())
    roots.sort(key=lambda b: b["title"].lower())
    return roots


def breadcrumbs(project_id: str, board_id: str) -> list[dict]:
    """Root-first path to this board. Guards against a parent cycle."""
    index = {b["id"]: b for b in all_boards(project_id)}
    trail, seen, current = [], set(), board_id
    while current and current in index and current not in seen:
        seen.add(current)
        board = index[current]
        trail.append({"id": board["id"], "title": board["title"]})
        current = board.get("parent_id")
    return list(reversed(trail))


def home_board(project_id: str) -> dict:
    """The board to open for this project, creating one if it has none."""
    project = load_project(project_id) or {}
    boards = all_boards(project_id)
    wanted = next((b for b in boards if b["id"] == project.get("home")), None)
    if wanted:
        return wanted
    roots = [b for b in boards if not b["parent_id"]] or boards
    if roots:
        roots.sort(key=lambda b: b["modified"], reverse=True)
        return roots[0]
    return create_board(project_id, "My board")


# --- assets ----------------------------------------------------------------


def save_asset(project_id: str, board_id: str, filename: str, data: bytes) -> str:
    """Store a file in the board's assets folder, return its relative src."""
    assets = board_dir(project_id, board_id) / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    stem, ext = os.path.splitext(os.path.basename(filename or "file"))
    stem = re.sub(r"[^A-Za-z0-9._-]", "_", stem)[:40] or "file"
    ext = re.sub(r"[^A-Za-z0-9.]", "", ext)[:10]
    name = f"{stem}_{secrets.token_hex(3)}{ext}"
    (assets / name).write_bytes(data)
    return f"assets/{name}"


def copy_asset(project_id: str, from_board: str, to_board: str, rel: str) -> str:
    """Copy one board's asset into another board's folder, returning the new src."""
    source = asset_path(project_id, from_board, rel)
    return save_asset(project_id, to_board, source.name, source.read_bytes())


def board_preview(project_id: str, board_id: str, limit: int = 60) -> list[dict]:
    """Just enough geometry to draw a miniature of a board on a board card."""
    board = load_board(project_id, board_id)
    if not board:
        return []
    keep = ("x", "y", "w", "h", "color", "type")
    return [{k: el.get(k) for k in keep} for el in board["elements"][:limit]]


def asset_path(project_id: str, board_id: str, rel: str) -> Path:
    """Resolve a board-relative asset path, refusing anything that escapes."""
    root = (board_dir(project_id, board_id) / "assets").resolve()
    target = (board_dir(project_id, board_id) / rel).resolve()
    if root != target and root not in target.parents:
        raise ValueError("asset path escapes board")
    return target


# --- search ----------------------------------------------------------------


def _element_text(el: dict) -> str:
    parts = [el.get("title", ""), el.get("text", ""), el.get("caption", "")]
    parts += [el.get("url", ""), el.get("desc", ""), el.get("name", "")]
    parts += [item.get("text", "") for item in el.get("items", [])]
    return re.sub(r"<[^>]+>", " ", " ".join(p for p in parts if p))


def search(project_id: str, query: str, limit: int = 40) -> list[dict]:
    query = query.strip().lower()
    if not query:
        return []
    hits: list[dict] = []
    for summary in all_boards(project_id):
        board = load_board(project_id, summary["id"])
        if not board:
            continue
        if query in board["title"].lower():
            hits.append({"board_id": board["id"], "board": board["title"],
                         "kind": "board", "text": board["title"]})
        for el in board["elements"]:
            text = _element_text(el)
            if query in text.lower():
                snippet = " ".join(text.split())
                where = snippet.lower().find(query)
                start = max(0, where - 30)
                hits.append({
                    "board_id": board["id"],
                    "board": board["title"],
                    "element_id": el["id"],
                    "kind": el.get("type", "note"),
                    "text": ("..." if start else "") + snippet[start:start + 120],
                })
            if len(hits) >= limit:
                return hits
    return hits


# --- first-run content -----------------------------------------------------


def _seed_welcome(project_id: str) -> dict:
    """The first-run welcome: a hub board that shows what Muse can do, with two
    real example boards behind board cards so nesting and templates are obvious.
    Everything is ordinary content the user can edit or delete."""
    from . import templates as template_module

    hub = blank_board("Welcome to Muse")

    # Two example boards from templates, nested under the hub so the sidebar
    # shows the hierarchy the board cards imply.
    examples = []
    for tid, title in (("moodboard", "Moodboard (example)"),
                       ("design-plan", "Project plan (example)")):
        spec = template_module.build(tid)
        if spec:
            spec["title"] = title
            examples.append(create_from_spec(project_id, spec, parent_id=hub["id"]))

    def element(kind, x, y, w, h, **rest):
        return {"id": new_id("e"), "type": kind, "x": x, "y": y,
                "w": w, "h": h, "parent": None, "color": "white", **rest}

    els = [
        element("text", 120, 80, 620, 54, color="none", text="Welcome to Muse"),
        element("note", 120, 170, 250, 165, color="yellow", title="Add anything",
                text="Drag a tool from the rail on the right onto the board. "
                     "Or just drop in images, PDFs and files, or paste a link."),
        element("note", 390, 170, 250, 165, color="blue", title="Your files, kept live",
                text="Drag in a folder to watch it, or link a file that stays in "
                     "sync. New renders show up here on their own. Right-click a "
                     "file to copy it into another app."),
        element("note", 660, 170, 250, 165, color="green", title="Show it off",
                text="Press F5 to present a board full screen, or use Export for a "
                     "PDF, image or web page you can send to a client."),
        element("todo", 120, 370, 300, 190, color="white", title="Try these",
                items=[
                    {"id": new_id("t"), "text": "Drag a note onto the board", "done": False},
                    {"id": new_id("t"), "text": "Drop in an image or PDF", "done": False},
                    {"id": new_id("t"), "text": "Open an example board below", "done": False},
                    {"id": new_id("t"), "text": "Press F5 to present", "done": False},
                    {"id": new_id("t"), "text": "Delete this project and start fresh", "done": False},
                ]),
        element("note", 440, 370, 470, 100, color="slate", title="Getting around",
                text="Space or middle-mouse drags the canvas. Ctrl and the wheel "
                     "zooms. Ctrl+Z undoes. Everything saves itself."),
    ]

    # Board cards linking to the example boards, with icons from the bi-* set.
    icons = ["svg:palette", "svg:note"]
    for i, ex in enumerate(examples):
        els.append(element("board", 440 + i * 250, 500, 230, 150,
                           board_id=ex["id"], title=ex["title"], icon=icons[i]))
        ex["icon"] = icons[i]
        save_board(project_id, ex)

    hub["elements"] = els
    save_board(project_id, hub)
    return hub
