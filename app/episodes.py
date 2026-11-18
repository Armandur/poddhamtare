"""Avsnittslistan i webbgränssnittet: flödet jämfört med filerna i mappen.

Läser bara. Webbprocessen sparar aldrig state, eftersom löpnummer som delas
ut här skulle kunna krocka med en samtidig körning av run.py.
"""
import logging
import threading
import time

from hamtare import feed, plan
from hamtare.state import State

log = logging.getLogger(__name__)

TTL = 300


def overview(cfg):
    return [_show(show, cfg) for show in cfg.shows]


def _show(show, cfg):
    out = {"name": show.name, "folder": str(show.output_dir), "error": None,
           "problems": [], "notes": [], "episodes": []}
    state_path = cfg.state_dir / f"{show.slug}.json"
    if not show.output_dir.is_dir():
        out["error"] = "Mappen finns inte. Kontrollera monteringen."
        return out
    if not state_path.exists():
        out["error"] = "Ingen state ännu. Kör 'retag --apply' först."
        return out
    try:
        f = feed.parse(feed.fetch(show.feed_url, cfg.user_agent))
    except Exception as exc:
        log.warning("Flödet för %s gick inte att hämta: %s", show.name, exc)
        out["error"] = "Flödet gick inte att hämta just nu."
        return out
    state = State(state_path)
    state.assign_numbers(f.episodes)  # bara i minnet, sparas aldrig här
    wanted = plan.desired(show, cfg, f, state)
    by_guid, untagged, problems = plan.scan(show.output_dir)
    out["problems"] = problems
    if untagged:
        out["problems"].append(f"{len(untagged)} mp3-filer saknar guid-tagg.")
    for d in wanted:
        hit = by_guid.get(d.episode.guid)
        if hit is None:
            status = "saknas"
        elif hit[0].name == d.filename and hit[1] == d.fp:
            status = "klar"
        else:
            status = "tagga"
        out["episodes"].append({
            "num": d.num, "date": d.fields["date"], "title": d.episode.title,
            "duration_s": d.episode.duration_s, "filename": d.filename, "status": status,
        })
    wanted_guids = {d.episode.guid for d in wanted}
    out["notes"] = [f"Finns inte längre i flödet: {p.name}"
                    for g, (p, _) in by_guid.items() if g not in wanted_guids]
    out["episodes"].reverse()  # nyast först
    return out


class Cache:
    def __init__(self, load):
        self._load = load
        self._lock = threading.Lock()
        self._data = None
        self._at = 0.0

    def get(self, refresh=False):
        with self._lock:
            if refresh or self._data is None or time.time() - self._at > TTL:
                self._data = self._load()
                self._at = time.time()
            return self._data, self._at

    def invalidate(self):
        self._at = 0.0
