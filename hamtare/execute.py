"""Utför en plan: hämtar och taggar via en dold .part-fil i målmappen och byter
sedan namn atomärt. Airsonic och podderi ser aldrig en halv fil."""
import hashlib
import logging
import os
import shutil

import httpx
from mutagen.mp3 import MP3

from hamtare import cover, tagging

log = logging.getLogger(__name__)


class DownloadError(Exception):
    pass


def ensure_folder_cover(show, cfg, feed, state, *, dry_run):
    """Lägger kanalbilden som cover.jpg i poddmappen, och byter den om URL:en ändrats."""
    target = show.output_dir / "cover.jpg"
    if not feed.image_url or (target.exists() and state.cover_url == feed.image_url):
        return False
    if dry_run:
        log.info("OMSLAG  skulle skriva %s", target)
        return True
    data = cover.jpeg(feed.image_url, cfg.state_dir / "covers", cfg.cover_size, cfg.user_agent)
    tmp = show.output_dir / ".cover.jpg.part"
    tmp.write_bytes(data)
    os.replace(tmp, target)
    state.cover_url = feed.image_url
    log.info("OMSLAG  skrev %s", target)
    return True


def run(plan, show, cfg, *, allow_download, limit=None):
    """-> (antal utförda, antal fel). Ett fel stoppar inte resten av planen."""
    done = failed = downloads = 0
    for action in plan.actions:
        if action.kind == "hamta":
            if not allow_download:
                continue
            if limit is not None and downloads >= limit:
                continue
            downloads += 1
        try:
            _apply(action, show, cfg)
            done += 1
        except Exception:
            failed += 1
            log.exception("FEL     %s %s", action.kind, action.desired.filename)
    return done, failed


def _apply(action, show, cfg):
    d = action.desired
    part = show.output_dir / f".{hashlib.sha1(d.episode.guid.encode()).hexdigest()[:12]}.part"
    dest = show.output_dir / d.filename
    try:
        if action.kind == "hamta":
            _download(d.episode.url, part, cfg.user_agent)
            _validate(part, d.episode.duration_s, cfg.min_duration_ratio)
        else:
            shutil.copyfile(action.src, part)
        cover_jpeg, fp = None, d.fp
        if d.cover_url:
            try:
                cover_jpeg = cover.jpeg(d.cover_url, cfg.state_dir / "covers",
                                        cfg.cover_size, cfg.user_agent)
            except (httpx.HTTPError, OSError) as exc:
                # Tomt fingeravtryck gör att nästa körning försöker igen.
                log.warning("Omslaget gick inte att hämta (%s), taggar utan: %s", exc, d.filename)
                fp = ""
        tagging.write(part, cover_jpeg=cover_jpeg, fp=fp, **d.fields)
        os.replace(part, dest)
        if action.src and action.src != dest:
            os.remove(action.src)
        log.info("%s %s", "HÄMTAD " if action.kind == "hamta" else "TAGGAD ", d.filename)
    finally:
        if part.exists():
            part.unlink()


def _download(url, part, user_agent):
    with httpx.stream("GET", url, headers={"User-Agent": user_agent},
                      follow_redirects=True, timeout=httpx.Timeout(60.0, read=120.0)) as resp:
        resp.raise_for_status()
        with open(part, "wb") as fh:
            for chunk in resp.iter_bytes(1 << 20):
                fh.write(chunk)


def _validate(part, duration_s, ratio):
    try:
        length = MP3(part).info.length
    except Exception as exc:
        raise DownloadError(f"inte en giltig mp3: {exc}") from exc
    if duration_s and length < duration_s * ratio:
        raise DownloadError(f"för kort: {length:.0f} s, flödet säger {duration_s} s")
