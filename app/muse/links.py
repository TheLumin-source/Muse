"""Turn a pasted URL into a card with a title, description and thumbnail."""

from __future__ import annotations

import html
import re
from urllib.parse import urljoin, urlparse

import httpx

from . import store

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Muse/0.1"
MAX_HTML = 512 * 1024
MAX_IMAGE = 4 * 1024 * 1024


def _meta(pattern: str, doc: str) -> str | None:
    match = re.search(pattern, doc, re.I | re.S)
    return html.unescape(match.group(1)).strip() if match else None


def _find(doc: str, *names: str) -> str | None:
    """First matching <meta> content for any of property/name = names."""
    for name in names:
        for attr in ("property", "name", "itemprop"):
            value = _meta(
                rf'<meta[^>]+{attr}=["\']{re.escape(name)}["\'][^>]*content=["\']([^"\']*)["\']',
                doc,
            ) or _meta(
                rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]*{attr}=["\']{re.escape(name)}["\']',
                doc,
            )
            if value:
                return value
    return None


def fetch_preview(url: str, project_id: str | None = None,
                  board_id: str | None = None) -> dict:
    """Best-effort metadata. Never raises: a bare link card still beats an error."""
    if not urlparse(url).scheme:
        url = "https://" + url
    parsed = urlparse(url)
    site = parsed.netloc.replace("www.", "")
    preview = {"url": url, "title": url, "desc": "", "site": site, "thumb": None}

    if parsed.scheme not in ("http", "https"):
        return preview

    try:
        with httpx.Client(
            follow_redirects=True, timeout=8.0, headers={"User-Agent": UA}
        ) as client:
            response = client.get(url)
            response.raise_for_status()
            doc = response.text[:MAX_HTML]
            final = str(response.url)

            title = _find(doc, "og:title", "twitter:title") or _meta(
                r"<title[^>]*>(.*?)</title>", doc
            )
            preview["title"] = " ".join(title.split()) if title else final
            desc = _find(doc, "og:description", "twitter:description", "description")
            preview["desc"] = " ".join(desc.split())[:280] if desc else ""
            preview["site"] = _find(doc, "og:site_name") or site

            image = _find(doc, "og:image", "twitter:image", "twitter:image:src")
            if image and project_id and board_id:
                preview["thumb"] = _grab_image(
                    client, urljoin(final, image), project_id, board_id)
    except Exception:
        pass  # offline, blocked, or not HTML - the plain card is still useful

    return preview


def _grab_image(client: httpx.Client, url: str,
                project_id: str, board_id: str) -> str | None:
    try:
        response = client.get(url)
        response.raise_for_status()
        if not response.headers.get("content-type", "").startswith("image/"):
            return None
        data = response.content[:MAX_IMAGE]
        name = urlparse(url).path.rsplit("/", 1)[-1] or "thumb.jpg"
        if "." not in name:
            name += ".jpg"
        return store.save_asset(project_id, board_id, name, data)
    except Exception:
        return None
