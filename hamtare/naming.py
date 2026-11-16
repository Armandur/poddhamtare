"""Filnamn och titeltagg enligt kafferepet-dl:s mönster:
'ÅÅÅÅ-MM-DD - 0045 - Titel.mp3' och titeltaggen '0045 - Titel'."""
import re
import unicodedata
from zoneinfo import ZoneInfo

from hamtare.feed import collapse_ws

LOCAL_TZ = ZoneInfo("Europe/Stockholm")
# Tecken som inte tillåts i filnamn (Windows/SMB). Tas bort, behålls i taggar.
_FORBIDDEN = str.maketrans({c: None for c in '/\\:*?"<>|'})
_MAX_NAME_BYTES = 240


def sanitize(text):
    return collapse_ws(text.translate(_FORBIDDEN))


def local_date(dt):
    return dt.astimezone(LOCAL_TZ).strftime("%Y-%m-%d")


def title_tag(num, title, padding):
    return f"{num:0{padding}d} - {title}"


def filename(date, num, title, padding, ext="mp3"):
    stem = f"{date} - {num:0{padding}d} - {sanitize(title)}"
    suffix = f".{ext}"
    while len((stem + suffix).encode("utf-8")) > _MAX_NAME_BYTES:
        stem = stem[:-1].rstrip()
    return stem + suffix


def match_key(text):
    """Jämförelsenyckel för titlar i gamla filnamn: bara bokstäver och siffror."""
    text = unicodedata.normalize("NFC", text).casefold()
    return re.sub(r"[\W_]+", "", text)
