"""Planerar vad som ska hända i en shows mapp: hämta, tagga om eller inget.

Filer känns igen på TXXX:PODCAST_GUID. Filer utan den taggen (Flexgets gamla
'ÅÅÅÅ-MM-DD - Titel.mp3') matchas bara i retag-läget, på datum och titel, och
bara om matchningen blir exakt en fil per avsnitt.
"""
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from hamtare import naming, tagging
from hamtare.feed import Episode

_OLD_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2}) - (.+?)\s*\.mp3$", re.I)


@dataclass(frozen=True)
class Desired:
    episode: Episode
    num: int
    filename: str
    fields: dict
    cover_url: str | None
    fp: str


@dataclass(frozen=True)
class Action:
    kind: str  # "hamta" | "tagga"
    desired: Desired
    src: Path | None


@dataclass
class Plan:
    actions: list[Action] = field(default_factory=list)
    ok: int = 0
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def desired(show, cfg, feed, state):
    album = show.album or feed.title
    artist = show.artist or feed.author
    out = []
    for ep in feed.episodes:
        num = state.numbers[ep.guid]
        day = naming.local_date(ep.published)
        fields = {
            "title": naming.title_tag(num, ep.title, cfg.number_padding),
            "album": album, "artist": artist, "genre": show.genre,
            "date": day, "track": num, "comment": ep.description, "guid": ep.guid,
        }
        cover_url = ep.image_url or feed.image_url
        out.append(Desired(
            episode=ep, num=num,
            filename=naming.filename(day, num, ep.title, cfg.number_padding),
            fields=fields, cover_url=cover_url,
            fp=tagging.fingerprint({**fields, "cover": cover_url}),
        ))
    return sorted(out, key=lambda d: d.num)


def scan(folder):
    """-> ({guid: (path, fingerprint)}, [filer utan guid], [problem])"""
    by_guid, untagged, problems = {}, [], []
    if not folder.is_dir():
        return by_guid, untagged, problems
    for p in sorted(folder.iterdir()):
        if p.name.startswith(".") or p.suffix.lower() != ".mp3" or not p.is_file():
            continue
        guid, fp = tagging.read_ids(p)
        if not guid:
            untagged.append(p)
        elif guid in by_guid:
            problems.append(f"Två filer har samma guid {guid}: {by_guid[guid][0].name} och {p.name}")
        else:
            by_guid[guid] = (p, fp)
    return by_guid, untagged, problems


def build(wanted, by_guid, untagged, *, match_untagged):
    plan = Plan()
    matched = {}
    if untagged and not match_untagged:
        plan.problems.append(
            f"{len(untagged)} mp3-filer saknar guid-tagg. Kör 'retag' först, "
            "annars hämtas avsnitten en gång till.")
        return plan
    if untagged:
        matched = _match(untagged, wanted, by_guid, plan.problems)
        if plan.problems:
            return plan

    sources = {g: p for g, (p, _) in by_guid.items()} | matched
    wanted_guids = {d.episode.guid for d in wanted}
    for guid, (p, _) in by_guid.items():
        if guid not in wanted_guids:
            plan.notes.append(f"Finns inte längre i flödet, lämnas orörd: {p.name}")

    for d in wanted:
        src = sources.get(d.episode.guid)
        dest = src.parent / d.filename if src else None
        if src is None:
            plan.actions.append(Action("hamta", d, None))
        elif src.name != d.filename or by_guid.get(d.episode.guid, (None, None))[1] != d.fp:
            if dest != src and dest.exists():
                plan.problems.append(f"Målnamnet finns redan: {d.filename}")
            plan.actions.append(Action("tagga", d, src))
        else:
            plan.ok += 1
    names = [d.filename for d in wanted]
    for n in {n for n in names if names.count(n) > 1}:
        plan.problems.append(f"Två avsnitt skulle få samma filnamn: {n}")
    return plan


def _match(untagged, wanted, by_guid, problems):
    """Matchar gamla filnamn mot avsnitt på titel och datum (±1 dygn, eftersom
    Flexget tog datumet i UTC). Kräver exakt en träff åt båda hållen."""
    by_key = {}
    for d in wanted:
        by_key.setdefault(naming.match_key(naming.sanitize(d.episode.title)), []).append(d)
    hits = {}
    for p in untagged:
        m = _OLD_NAME.match(p.name)
        if not m:
            problems.append(f"Känner inte igen filnamnet: {p.name}")
            continue
        day = date.fromisoformat(m.group(1))
        cands = [d for d in by_key.get(naming.match_key(m.group(2)), [])
                 if abs(date.fromisoformat(d.fields["date"]) - day) <= timedelta(days=1)]
        if len(cands) != 1:
            problems.append(f"{len(cands)} avsnitt matchar filen, väntade 1: {p.name}")
            continue
        guid = cands[0].episode.guid
        if guid in by_guid:
            problems.append(f"Avsnittet finns redan som {by_guid[guid][0].name}, dubblett: {p.name}")
        elif guid in hits:
            problems.append(f"Två filer matchar samma avsnitt: {hits[guid].name} och {p.name}")
        else:
            hits[guid] = p
    return hits
