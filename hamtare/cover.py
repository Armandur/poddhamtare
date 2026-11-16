"""Hämtar omslag och skalar ned dem till JPEG. Cachas per URL i STATE_DIR/covers."""
import hashlib
import io
import os
from pathlib import Path

import httpx
from PIL import Image


def jpeg(url, cache_dir, size, user_agent):
    cache = Path(cache_dir) / f"{hashlib.sha1(url.encode()).hexdigest()}_{size}.jpg"
    if cache.exists():
        return cache.read_bytes()
    resp = httpx.get(url, headers={"User-Agent": user_agent}, timeout=60.0,
                     follow_redirects=True)
    resp.raise_for_status()
    img = Image.open(io.BytesIO(resp.content)).convert("RGB")
    img.thumbnail((size, size))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=88, optimize=True)
    data = out.getvalue()
    cache.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_suffix(".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, cache)
    return data
