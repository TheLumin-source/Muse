"""Render a board to a flat image, then save it as PDF and PNG.

This is the print/deliverable path: a client gets a clean picture of the board.
It draws with Pillow rather than a browser engine, reusing the same layout the
canvas uses. Live and PDF cards are drawn from their current thumbnails, so the
export reflects the files as they are now.
"""

from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import livefiles, platform, store

EXPORTS = store.DATA_ROOT / "Exports"
PAD = 90
SCALE = 2                      # supersample for crisp text
MAX_PX = 6000                  # cap the long side

COLORS = {
    "white": "#ffffff", "yellow": "#fdf3c8", "orange": "#ffe0c2", "red": "#ffcfc9",
    "coral": "#ffd6c2", "pink": "#ffd9e2", "rose": "#ffcada", "purple": "#e6dcff",
    "indigo": "#d5d3ff", "blue": "#d4e6ff", "sky": "#cdecff", "teal": "#cdeee6",
    "green": "#dcf0c8", "lime": "#e9f2c2", "amber": "#ffeec2", "slate": "#dfe1e6",
    "gray": "#d3d5db", "none": None, "code": "#2a2d36",
}
INK = "#24211c"
DIM = "#8a8378"
LINE = "#d9d3c8"


def _font(role: str, px: int) -> ImageFont.FreeTypeFont:
    """Resolve a font ROLE (not a filename) so each platform can answer with
    whatever it actually ships. See platform.font_path."""
    found = platform.font_path(role)
    if found:
        try:
            return ImageFont.truetype(found, px)
        except OSError:
            pass
    return ImageFont.load_default()


def _resolve_color(value: str | None) -> str | None:
    if not value:
        return None
    if value.startswith("#"):
        return value
    return COLORS.get(value, "#ffffff")


def _wrap(draw, text: str, font, max_w: float) -> list[str]:
    lines = []
    for paragraph in (text or "").split("\n"):
        if not paragraph:
            lines.append("")
            continue
        words, line = paragraph.split(" "), ""
        for word in words:
            trial = f"{line} {word}".strip()
            if draw.textlength(trial, font=font) <= max_w or not line:
                line = trial
            else:
                lines.append(line)
                line = word
        lines.append(line)
    return lines


def _strip_html(text: str) -> str:
    import re
    text = re.sub(r"<br\s*/?>", "\n", text or "", flags=re.I)
    text = re.sub(r"</(p|div|li)>", "\n", text, flags=re.I)
    text = re.sub(r"<li>", "- ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    import html as _html
    return _html.unescape(text).strip()


def _rounded(draw, box, radius, fill=None, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _paste_cover(canvas, img_path, box):
    """Paste an image cropped to cover the box."""
    try:
        with Image.open(img_path) as im:
            im = im.convert("RGB")
    except Exception:
        return False
    bx, by, bw, bh = box[0], box[1], box[2] - box[0], box[3] - box[1]
    if bw <= 0 or bh <= 0:
        return False
    scale = max(bw / im.width, bh / im.height)
    im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.LANCZOS)
    ox = (im.width - bw) // 2
    oy = (im.height - bh) // 2
    canvas.paste(im.crop((ox, oy, ox + bw, oy + bh)), (int(bx), int(by)))
    return True


def _asset(project_id, board_id, src):
    try:
        return store.asset_path(project_id, board_id, src)
    except ValueError:
        return None


# --- connector geometry (matches the canvas) --------------------------------


def _rect_of(end, by_id):
    if isinstance(end, str):
        el = by_id.get(end)
        if not el:
            return None
        return (el["x"], el["y"], el["w"], el["h"])
    return (end["x"], end["y"], 0, 0)


def _anchor(rect, other):
    x, y, w, h = rect
    cx, cy = x + w / 2, y + h / 2
    ox, oy = other[0] + other[2] / 2, other[1] + other[3] / 2
    if abs(ox - cx) * (h + 1) > abs(oy - cy) * (w + 1):
        return (x + w, cy) if ox > cx else (x, cy)
    return (cx, y + h) if oy > cy else (cx, y)


def render_board(project_id: str, board_id: str) -> dict:
    board = store.load_board(project_id, board_id)
    if not board:
        raise ValueError("no such board")
    els = board.get("elements", [])
    by_id = {e["id"]: e for e in els}

    if els:
        min_x = min(e["x"] for e in els) - PAD
        min_y = min(e["y"] for e in els) - PAD
        max_x = max(e["x"] + e["w"] for e in els) + PAD
        max_y = max(e["y"] + e["h"] for e in els) + PAD
    else:
        min_x = min_y = 0
        max_x = max_y = 600

    world_w, world_h = max_x - min_x, max_y - min_y
    scale = min(SCALE, MAX_PX / max(world_w, world_h, 1))
    W, H = int(world_w * scale), int(world_h * scale)

    def sx(v): return int((v - min_x) * scale)
    def sy(v): return int((v - min_y) * scale)
    def sc(v): return max(1, int(v * scale))

    img = Image.new("RGB", (W, H), "#f2efe8")
    draw = ImageDraw.Draw(img)

    f_title = _font("sans-bold", sc(14))
    f_body = _font("sans", sc(13))
    f_head = _font("sans-bold", sc(26))
    f_small = _font("sans", sc(11))
    f_mono = _font("mono", sc(12))

    # columns first, so children sit above them
    ordered = sorted(els, key=lambda e: 0 if e.get("type") == "column" else 1)

    # connectors under the cards
    for wire in board.get("connectors", []):
        a = _rect_of(wire["from"], by_id)
        b = _rect_of(wire["to"], by_id)
        if not a or not b:
            continue
        p1 = _anchor(a, b)
        p2 = _anchor(b, a)
        draw.line([(sx(p1[0]), sy(p1[1])), (sx(p2[0]), sy(p2[1]))],
                  fill="#8b8377", width=max(1, sc(2)))

    for el in ordered:
        _draw_card(el, img, draw, project_id, board_id, sx, sy, sc,
                   f_title, f_body, f_head, f_small, f_mono)

    EXPORTS.mkdir(parents=True, exist_ok=True)
    import re as _re
    safe = _re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", board.get("title", "Board")).strip() or "Board"
    stamp = datetime.now().strftime("%Y-%m-%d %H%M")
    pdf = EXPORTS / f"{safe} {stamp}.pdf"
    png = EXPORTS / f"{safe} {stamp}.png"
    img.save(png)
    img.save(pdf, "PDF", resolution=96.0)
    return {"pdf": str(pdf), "png": str(png)}


def _draw_card(el, img, draw, project_id, board_id, sx, sy, sc,
               f_title, f_body, f_head, f_small, f_mono):
    kind = el.get("type", "note")
    x0, y0, x1, y1 = sx(el["x"]), sy(el["y"]), sx(el["x"] + el["w"]), sy(el["y"] + el["h"])
    box = (x0, y0, x1, y1)
    r = sc(11)
    pad = sc(11)
    color = _resolve_color(el.get("color"))

    if kind == "text":
        for i, line in enumerate(_wrap(draw, _strip_html(el.get("text", "")), f_head, x1 - x0)):
            draw.text((x0, y0 + i * sc(32)), line, font=f_head, fill="#2c2823")
        return

    if kind == "image":
        _rounded(draw, box, r, fill="#ece7dd")
        src = el.get("src")
        path = _asset(project_id, board_id, src) if src else None
        if not (path and path.exists() and _paste_cover(img, path, box)):
            draw.text((x0 + pad, y0 + pad), "image", font=f_small, fill=DIM)
        if el.get("caption"):
            draw.text((x0 + pad, y1 - sc(18)), el["caption"][:60], font=f_small, fill="#fff")
        return

    if kind in ("live", "watch"):
        _rounded(draw, box, r, fill="#ffffff", outline=LINE, width=sc(1))
        thumb = livefiles.thumbnail(el.get("path", ""), 480) if kind == "live" else None
        if thumb and _paste_cover(img, thumb, (x0, y0, x1, y1 - sc(30))):
            pass
        else:
            draw.text((x0 + pad, y0 + pad), el.get("name") or el.get("title") or el.get("path", ""),
                      font=f_small, fill=DIM)
        label = el.get("name") or el.get("title") or ""
        draw.text((x0 + pad, y1 - sc(22)), label[:48], font=f_small, fill=INK)
        return

    if kind == "code":
        _rounded(draw, box, r, fill="#22252c")
        draw.text((x0 + pad, y0 + sc(6)), (el.get("lang") or "code"), font=f_small, fill="#8b8f9c")
        yy = y0 + sc(26)
        for line in (el.get("code", "").split("\n"))[:40]:
            draw.text((x0 + pad, yy), line[:120], font=f_mono, fill="#e6e6e6")
            yy += sc(16)
            if yy > y1 - sc(10):
                break
        return

    if kind == "board":
        _rounded(draw, box, r, fill=color or "#ffffff", outline=LINE, width=sc(1))
        icon = (el.get("icon") or "") + " " if el.get("icon") else ""
        draw.text((x0 + pad, y0 + pad), f"{icon}{el.get('title', 'Board')}", font=f_title, fill=INK)
        draw.text((x0 + pad, y0 + pad + sc(22)), "board", font=f_small, fill=DIM)
        return

    if kind == "column":
        _rounded(draw, box, r, fill=color or "#dfe1e6")
        draw.text((x0 + pad, y0 + sc(8)), el.get("title", ""), font=f_title, fill="#4a453d")
        return

    if kind == "link":
        _rounded(draw, box, r, fill="#ffffff", outline=LINE, width=sc(1))
        th = el.get("thumb")
        tpath = _asset(project_id, board_id, th) if th else None
        split = y0 + (y1 - y0) // 2
        if tpath and tpath.exists():
            _paste_cover(img, tpath, (x0, y0, x1, split))
            ty = split + sc(8)
        else:
            ty = y0 + pad
        draw.text((x0 + pad, ty), (el.get("title") or el.get("url", ""))[:80], font=f_title, fill=INK)
        draw.text((x0 + pad, ty + sc(20)), el.get("site", "")[:60], font=f_small, fill=DIM)
        return

    if kind == "file":
        _rounded(draw, box, r, fill="#ffffff", outline=LINE, width=sc(1))
        th = el.get("thumb")
        tpath = _asset(project_id, board_id, th) if th else None
        if tpath and tpath.exists():
            _paste_cover(img, tpath, (x0, y0, x1, y1 - sc(28)))
            draw.text((x0 + pad, y1 - sc(22)), (el.get("name") or "File")[:48], font=f_small, fill=INK)
        else:
            draw.text((x0 + pad, y0 + pad), (el.get("ext") or "file").upper(), font=f_title, fill=DIM)
            draw.text((x0 + pad, y0 + pad + sc(22)), (el.get("name") or "File")[:48], font=f_body, fill=INK)
        return

    if kind == "todo":
        _rounded(draw, box, r, fill=color or "#ffffff", outline=LINE, width=sc(1))
        draw.text((x0 + pad, y0 + sc(8)), el.get("title", ""), font=f_title, fill=INK)
        yy = y0 + sc(30)
        for item in el.get("items", []):
            bx = x0 + pad
            draw.rounded_rectangle((bx, yy, bx + sc(14), yy + sc(14)), radius=sc(3),
                                   outline="#b3ab9c", width=sc(1),
                                   fill="#55a763" if item.get("done") else None)
            draw.text((bx + sc(22), yy), (item.get("text", ""))[:60], font=f_body, fill=INK)
            yy += sc(24)
            if yy > y1 - sc(8):
                break
        return

    # default: note
    _rounded(draw, box, r, fill=color or "#ffffff", outline=LINE, width=sc(1))
    yy = y0 + pad
    if el.get("title"):
        draw.text((x0 + pad, yy), el["title"][:60], font=f_title, fill=INK)
        yy += sc(22)
    for line in _wrap(draw, _strip_html(el.get("text", "")), f_body, x1 - x0 - pad * 2):
        draw.text((x0 + pad, yy), line, font=f_body, fill=INK)
        yy += sc(18)
        if yy > y1 - sc(6):
            break
