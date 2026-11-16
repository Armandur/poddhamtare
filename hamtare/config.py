"""Läser config.yaml till dataklasser."""
import os
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Show:
    name: str
    slug: str
    feed_url: str
    output_dir: Path
    album: str | None
    artist: str | None
    genre: str


@dataclass(frozen=True)
class Config:
    state_dir: Path
    user_agent: str
    number_padding: int
    cover_size: int
    min_duration_ratio: float
    shows: list[Show]


def load(path):
    raw = yaml.safe_load(Path(path).read_text("utf-8")) or {}
    d = raw.get("defaults", {})
    shows = []
    for s in raw.get("shows", []):
        for key in ("name", "slug", "feed_url", "output_dir"):
            if not s.get(key):
                raise ValueError(f"config: show saknar '{key}': {s}")
        shows.append(Show(
            name=s["name"], slug=s["slug"], feed_url=s["feed_url"],
            output_dir=Path(s["output_dir"]), album=s.get("album"),
            artist=s.get("artist"), genre=s.get("genre", "Podcast"),
        ))
    if not shows:
        raise ValueError("config: inga shows")
    return Config(
        state_dir=Path(os.environ.get("STATE_DIR", d.get("state_dir", "/state"))),
        user_agent=d.get("user_agent", "poddhamtare/1.0"),
        number_padding=int(d.get("number_padding", 4)),
        cover_size=int(d.get("cover_size", 1000)),
        min_duration_ratio=float(d.get("min_duration_ratio", 0.9)),
        shows=shows,
    )
