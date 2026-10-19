"""Export a board as one self-contained HTML file.

Everything is inlined - images become data URIs, connectors become inline SVG -
so the file can be emailed to a client and opened with a double-click, no
account, no server, no internet. Live-file cards are frozen at export time:
the file shows what the linked file looked like when you exported.
"""

from __future__ import annotations

import base64
import html
import math
import re
from datetime import datetime
from pathlib import Path

from . import livefiles, store

EXPORTS = store.DATA_ROOT / "Exports"
PAD = 80

COLORS = {
    "white": "#ffffff", "yellow": "#fdf3c8", "orange": "#ffe0c2",
    "pink": "#ffd9e2", "purple": "#e6dcff", "blue": "#d4e6ff",
    "teal": "#cdeee6", "green": "#dcf0c8", "slate": "#dfe1e6",
}

MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp"}


def _data_uri(path: Path) -> str | None:
    try:
        mime = MIME.get(path.suffix.lower(), "application/octet-stream")
        return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"
    except OSError:
        return None


# --- connector geometry, same maths as the canvas ---------------------------


def _rect_of(end, elements):
    if isinstance(end, str):
        el = elements.get(end)
        if not el:
            return None
        return {"x": el["x"], "y": el["y"], "w": el["w"], "h": el["h"],
                "cx": el["x"] + el["w"] / 2, "cy": el["y"] + el["h"] / 2}
    return {"x": end["x"], "y": end["y"], "w": 0, "h": 0,
            "cx": end["x"], "cy": end["y"]}


def _side(a, b):
    dx, dy = b["cx"] - a["cx"], b["cy"] - a["cy"]
    if abs(dx) * (a["h"] + 1) > abs(dy) * (a["w"] + 1):
        return "e" if dx > 0 else "w"
    return "s" if dy > 0 else "n"


def _anchor(rect, side):
    if side == "n":
        return rect["cx"], rect["y"], 0, -1
    if side == "s":
        return rect["cx"], rect["y"] + rect["h"], 0, 1
    if side == "w":
        return rect["x"], rect["cy"], -1, 0
    return rect["x"] + rect["w"], rect["cy"], 1, 0


def _curve(f, t):
    pull = max(26.0, min(150.0, math.hypot(t[0] - f[0], t[1] - f[1]) * 0.42))
    return (f"M {f[0]:.0f} {f[1]:.0f} "
            f"C {f[0] + f[2] * pull:.0f} {f[1] + f[3] * pull:.0f}, "
            f"{t[0] + t[2] * pull:.0f} {t[1] + t[3] * pull:.0f}, "
            f"{t[0]:.0f} {t[1]:.0f}")


# --- element rendering -------------------------------------------------------


def _card_html(el: dict, project_id: str, board_id: str) -> str:
    kind = el.get("type", "note")
    color = COLORS.get(el.get("color", "white"), "#ffffff")
    style = (f'left:{el["x"]}px;top:{el["y"]}px;'
             f'width:{el["w"]}px;height:{el["h"]}px;')
    esc = html.escape

    if kind == "text":
        return (f'<div class="el text" style="{style}">'
                f'<div class="heading">{el.get("text", "")}</div></div>')

    if kind == "note":
        title = f'<div class="title">{esc(el.get("title", ""))}</div>' if el.get("title") else ""
        return (f'<div class="el note" style="{style}background:{color}">'
                f'{title}<div class="rich">{el.get("text", "")}</div></div>')

    if kind == "todo":
        rows = "".join(
            f'<div class="item{" done" if item.get("done") else ""}">'
            f'<span class="box"></span><span>{esc(item.get("text", ""))}</span></div>'
            for item in el.get("items", []))
        return (f'<div class="el note" style="{style}background:{color}">'
                f'<div class="title">{esc(el.get("title", ""))}</div>{rows}</div>')

    if kind == "image":
        uri = None
        if el.get("src"):
            try:
                uri = _data_uri(store.asset_path(project_id, board_id, el["src"]))
            except ValueError:
                uri = None
        body = (f'<img src="{uri}" alt="">' if uri
                else '<div class="ph">image</div>')
        cap = (f'<div class="cap">{esc(el.get("caption", ""))}</div>'
               if el.get("caption") else "")
        return f'<div class="el img" style="{style}">{body}{cap}</div>'

    if kind == "live":
        thumb = livefiles.thumbnail(el.get("path", ""), 480)
        uri = _data_uri(thumb) if thumb else None
        body = (f'<img src="{uri}" alt="">' if uri
                else f'<div class="ph">{esc(el.get("kind", "file"))}</div>')
        return (f'<div class="el img live" style="{style}">{body}'
                f'<div class="lfoot">{esc(el.get("name", ""))}</div></div>')

    if kind == "watch":
        listing = livefiles.listing(el.get("path", ""), el.get("kinds", "images"),
                                    el.get("limit", 12))
        cells = []
        for file in listing["files"]:
            thumb = livefiles.thumbnail(file["path"], 200)
            uri = _data_uri(thumb) if thumb else None
            cells.append(f'<i>{f"<img src={chr(34)}{uri}{chr(34)}>" if uri else ""}</i>')
        title = esc(el.get("title") or Path(el.get("path", "")).name)
        return (f'<div class="el watch" style="{style}">'
                f'<div class="whead">{title}</div>'
                f'<div class="wgrid">{"".join(cells)}</div></div>')

    if kind == "link":
        thumb = ""
        if el.get("thumb"):
            try:
                uri = _data_uri(store.asset_path(project_id, board_id, el["thumb"]))
                if uri:
                    thumb = f'<div class="thumb" style="background-image:url({uri})"></div>'
            except ValueError:
                pass
        return (f'<a class="el link" style="{style}" href="{esc(el.get("url", "#"))}" '
                f'target="_blank" rel="noopener">{thumb}'
                f'<div class="meta"><b>{esc(el.get("title", ""))}</b>'
                f'<span>{esc(el.get("site", ""))}</span></div></a>')

    if kind == "file":
        ext = esc((el.get("ext") or "file")[:4].upper())
        return (f'<div class="el filecard" style="{style}">'
                f'<span class="ext">{ext}</span>'
                f'<span class="fname">{esc(el.get("name", "File"))}</span></div>')

    if kind == "board":
        return (f'<div class="el boardcard" style="{style}">'
                f'<div class="btitle">{esc(el.get("title", "Board"))}</div>'
                f'<div class="bnote">board</div></div>')

    if kind == "column":
        return (f'<div class="el col" style="{style}">'
                f'<div class="chead">{esc(el.get("title", ""))}</div></div>')

    return ""


CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body { margin: 0; font: 14px/1.45 "Segoe UI", system-ui, sans-serif; color: #24211c;
  background: #f2efe8 radial-gradient(#d5d0c5 1.1px, transparent 1.1px); background-size: 22px 22px; }
header { position: sticky; top: 0; z-index: 5; padding: 14px 22px; background: #202128; color: #e8e6e1; }
header h1 { margin: 0; font-size: 16px; font-weight: 640; }
header span { font-size: 12px; opacity: .55; }
#canvas { position: relative; margin: 0 auto; }
svg.wires { position: absolute; left: 0; top: 0; overflow: visible; pointer-events: none; }
svg.wires path { fill: none; stroke: #7a7266; stroke-width: 2; }
.el { position: absolute; border-radius: 10px; background: #fff; border: 1px solid rgba(30,28,24,.13);
  box-shadow: 0 1px 2px rgba(40,36,30,.10), 0 6px 16px rgba(40,36,30,.10); padding: 10px 12px; overflow: hidden; }
.el.text { background: none; border: none; box-shadow: none; padding: 0; }
.heading { font-size: 27px; font-weight: 680; letter-spacing: -.015em; color: #2c2823; line-height: 1.22; }
.title { font-weight: 640; margin-bottom: 3px; }
.rich { font-size: 13.5px; white-space: pre-wrap; overflow-wrap: anywhere; }
.item { display: flex; gap: 7px; padding: 2px 0; font-size: 13.5px; align-items: flex-start; }
.item .box { width: 15px; height: 15px; margin-top: 2px; flex: none; border-radius: 4px; border: 1.6px solid #b3ab9c; }
.item.done .box { background: #55a763; border-color: #55a763; position: relative; }
.item.done .box::after { content: ""; position: absolute; left: 4px; top: 1px; width: 4px; height: 8px;
  border: solid #fff; border-width: 0 2px 2px 0; transform: rotate(42deg); }
.item.done span:last-child { text-decoration: line-through; color: #9a9184; }
.el.img { padding: 0; }
.el.img img { width: 100%; height: 100%; object-fit: cover; display: block; }
.el.img .ph { display: flex; align-items: center; justify-content: center; height: 100%; color: #a09889; }
.el.img .cap, .el.img .lfoot { position: absolute; left: 0; right: 0; bottom: 0; padding: 14px 10px 6px;
  font-size: 12px; color: #fff; background: linear-gradient(transparent, rgba(0,0,0,.62)); }
.el.watch { padding: 0; }
.whead { padding: 9px 11px 6px; font-weight: 620; font-size: 13px; }
.wgrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(64px, 1fr)); gap: 5px; padding: 0 10px 10px; }
.wgrid i { aspect-ratio: 1; border-radius: 6px; overflow: hidden; background: #ece7dd; display: block; }
.wgrid img { width: 100%; height: 100%; object-fit: cover; display: block; }
a.el.link { text-decoration: none; color: inherit; padding: 0; display: block; }
.link .thumb { height: 55%; background: #ece7dd center/cover no-repeat; }
.link .meta { padding: 8px 11px; }
.link .meta b { display: block; font-size: 13px; }
.link .meta span { font-size: 11px; color: #9d958a; }
.el.filecard { display: flex; align-items: center; gap: 10px; }
.filecard .ext { padding: 8px 9px; border-radius: 5px; background: #e9e3d8; font-size: 10px; font-weight: 700; color: #6d6558; }
.filecard .fname { font-size: 13px; }
.el.boardcard { background: #fff; }
.btitle { font-weight: 640; font-size: 13.5px; }
.bnote { font-size: 11px; color: #9d958a; margin-top: 4px; }
.el.col { background: rgba(255,255,255,.55); }
.chead { font-weight: 640; font-size: 13px; color: #4a453d; }
footer { padding: 18px 22px 30px; font-size: 11.5px; color: #8d857a; text-align: center; }
"""


def export_board(project_id: str, board_id: str) -> Path:
    board = store.load_board(project_id, board_id)
    if not board:
        raise ValueError("no such board")
    elements = board.get("elements", [])
    by_id = {el["id"]: el for el in elements}

    if elements:
        min_x = min(el["x"] for el in elements) - PAD
        min_y = min(el["y"] for el in elements) - PAD
        max_x = max(el["x"] + el["w"] for el in elements) + PAD
        max_y = max(el["y"] + el["h"] for el in elements) + PAD
    else:
        min_x = min_y = 0
        max_x = max_y = 400

    # Shift everything so the top-left card sits near the origin.
    shifted = []
    for el in elements:
        el = dict(el)
        el["x"] -= min_x
        el["y"] -= min_y
        shifted.append(el)
    shifted_ids = {el["id"]: el for el in shifted}

    # Columns first so their children draw on top of them.
    shifted.sort(key=lambda e: 0 if e.get("type") == "column" else 1)
    cards = "".join(_card_html(el, project_id, board_id) for el in shifted)

    paths = []
    for wire in board.get("connectors", []):
        a = _rect_of(wire["from"], shifted_ids)
        b = _rect_of(
            wire["to"] if isinstance(wire["to"], str)
            else {"x": wire["to"]["x"] - min_x, "y": wire["to"]["y"] - min_y},
            shifted_ids)
        if not a or not b:
            continue
        f = _anchor(a, _side(a, b))
        t = _anchor(b, _side(b, a))
        marker = ' marker-end="url(#arr)"' if wire.get("arrow") != "none" else ""
        paths.append(f'<path d="{_curve(f, t)}"{marker}/>')

    width = int(max_x - min_x)
    height = int(max_y - min_y)
    title = html.escape(board.get("title", "Board"))
    stamp = datetime.now().strftime("%d %B %Y, %H:%M")

    doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title><style>{CSS}</style></head>
<body>
<header><h1>{title}</h1><span>exported from Muse, {stamp}</span></header>
<div id="canvas" style="width:{width}px;height:{height}px">
<svg class="wires" width="{width}" height="{height}">
<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7"
 markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="#7a7266"/></marker></defs>
{"".join(paths)}</svg>
{cards}
</div>
<footer>{title} - made with Muse</footer>
</body></html>"""

    EXPORTS.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", board.get("title", "Board")).strip() or "Board"
    out = EXPORTS / f"{safe} {datetime.now():%Y-%m-%d %H%M}.html"
    out.write_text(doc, encoding="utf-8")
    return out
