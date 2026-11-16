"""Läser poddens RSS-flöde till Feed/Episode. Bara stdlib-XML, ingen feedparser."""
import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

_ITUNES = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"


@dataclass(frozen=True)
class Episode:
    guid: str
    title: str
    published: datetime  # tidszonsmedveten
    url: str
    duration_s: int | None
    image_url: str | None
    description: str


@dataclass(frozen=True)
class Feed:
    title: str
    author: str
    image_url: str | None
    episodes: list[Episode]  # äldst först


def fetch(url, user_agent, timeout=30.0):
    resp = httpx.get(url, headers={"User-Agent": user_agent}, timeout=timeout,
                     follow_redirects=True)
    resp.raise_for_status()
    return resp.content


def parse(xml_bytes):
    root = ET.fromstring(xml_bytes)
    ch = root.find("channel")
    if ch is None:
        raise ValueError("flödet saknar <channel>")
    episodes = [ep for item in ch.findall("item") if (ep := _episode(item))]
    episodes.sort(key=lambda e: e.published)
    return Feed(
        title=_text(ch, "title"),
        author=_text(ch, f"{_ITUNES}author") or _text(ch, "copyright"),
        image_url=_image(ch),
        episodes=episodes,
    )


def _episode(item):
    enc = item.find("enclosure")
    url = enc.get("url") if enc is not None else None
    title = _text(item, "title") or _text(item, f"{_ITUNES}title")
    published = _date(item.findtext("pubDate"))
    guid = _text(item, "guid") or url
    if not (url and title and published and guid):
        return None
    return Episode(
        guid=guid,
        title=collapse_ws(title),
        published=published,
        url=url,
        duration_s=_duration(item.findtext(f"{_ITUNES}duration")),
        image_url=_image(item),
        description=html_to_text(item.findtext("description") or ""),
    )


def _text(el, tag):
    return (el.findtext(tag) or "").strip()


def _image(el):
    img = el.find(f"{_ITUNES}image")
    if img is not None and img.get("href"):
        return img.get("href").strip()
    url = el.findtext("image/url")
    return url.strip() if url else None


def _date(text):
    if not text:
        return None
    try:
        dt = parsedate_to_datetime(text.strip())
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _duration(text):
    """'1:04:46' / '54:12' / '3252' -> sekunder."""
    if not text:
        return None
    secs = 0
    try:
        for part in text.strip().split(":"):
            secs = secs * 60 + int(part)
    except ValueError:
        return None
    return secs


def collapse_ws(text):
    return re.sub(r"\s+", " ", text).strip()


def html_to_text(raw):
    """Avsnittsbeskrivning i HTML -> ren text. Acasts sidfot efter <hr> tas bort."""
    raw = re.split(r"<hr\s*/?>", raw, maxsplit=1, flags=re.I)[0]
    raw = re.sub(r"(?i)<br\s*/?>", "\n", raw)
    raw = re.sub(r"(?i)</p\s*>", "\n\n", raw)
    raw = re.sub(r"<[^>]+>", "", raw)
    text = html.unescape(raw)
    lines = [collapse_ws(line) for line in text.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
