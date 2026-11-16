import shutil
from pathlib import Path

import pytest
from mutagen.id3 import ID3, TIT2

import run as cli
from hamtare import config, execute, feed, naming, plan, tagging
from hamtare.state import State

DATA = Path(__file__).parent / "data"

FEED_XML = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
<channel>
  <title>Torsdagsdeppen</title>
  <itunes:author>Kyrkans Tidning</itunes:author>
  <itunes:image href="https://bild.example/kanal.jpeg"/>
  <item>
    <title>Edgate, döden på konfa</title>
    <pubDate>Thu, 09 Jul 2026 04:30:00 GMT</pubDate>
    <itunes:duration>53:24</itunes:duration>
    <enclosure url="https://ljud.example/c.mp3" length="1" type="audio/mpeg"/>
    <guid isPermaLink="false">guid-c</guid>
    <itunes:episode>31</itunes:episode>
    <description>&lt;p&gt;Text &amp;amp; mer.&lt;/p&gt;&lt;hr&gt;&lt;p&gt;Hosted on Acast.&lt;/p&gt;</description>
  </item>
  <item>
    <title>Torsdagsdeppens stora gräv</title>
    <pubDate>Thu, 02 Jul 2026 04:30:00 GMT</pubDate>
    <enclosure url="https://ljud.example/b.mp3" length="1" type="audio/mpeg"/>
    <guid isPermaLink="false">guid-b</guid>
    <itunes:episode>31</itunes:episode>
    <itunes:image href="https://bild.example/b.jpeg"/>
  </item>
  <item>
    <title>Är Joel Halldorf en vampyr? Och varför heter alla Emanuel i kyrkan?</title>
    <pubDate>Fri, 07 Nov 2025 23:30:00 GMT</pubDate>
    <enclosure url="https://ljud.example/a.mp3" length="1" type="audio/mpeg"/>
    <guid isPermaLink="false">guid-a</guid>
  </item>
</channel>
</rss>""".encode()


@pytest.fixture
def setup(tmp_path):
    out = tmp_path / "podd"
    out.mkdir()
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "defaults:\n  number_padding: 4\nshows:\n"
        f"  - name: T\n    slug: t\n    feed_url: https://x\n    output_dir: {out}\n"
        "    album: Torsdagsdeppen\n    artist: Kyrkans Tidning\n", "utf-8")
    cfg = config.load(cfg_file)
    cfg = config.Config(**{**cfg.__dict__, "state_dir": tmp_path / "state"})
    return cfg, cfg.shows[0], out


def _wanted(cfg, show):
    f = feed.parse(FEED_XML)
    st = State(cfg.state_dir / "t.json")
    st.assign_numbers(f.episodes)
    return f, st, plan.desired(show, cfg, f, st)


def _mp3(path):
    shutil.copyfile(DATA / "tyst.mp3", path)
    tags = ID3()
    tags.add(TIT2(encoding=3, text=["Untitled"]))
    tags.save(path)
    return path


def test_feed_parse_ordning_datum_och_beskrivning():
    f = feed.parse(FEED_XML)
    assert [e.guid for e in f.episodes] == ["guid-a", "guid-b", "guid-c"]
    assert f.episodes[2].duration_s == 53 * 60 + 24
    assert f.episodes[2].description == "Text & mer."
    assert f.episodes[0].image_url is None and f.image_url == "https://bild.example/kanal.jpeg"


def test_lopnummer_ignorerar_flodets_dubbletter_och_ar_stabila(tmp_path):
    f = feed.parse(FEED_XML)
    st = State(tmp_path / "s.json")
    st.assign_numbers(f.episodes)
    assert st.numbers == {"guid-a": 1, "guid-b": 2, "guid-c": 3}
    st.save()
    nytt = feed.Episode("guid-0", "Äldre", f.episodes[0].published, "u", None, None, "")
    st2 = State(tmp_path / "s.json")
    st2.assign_numbers([nytt, *f.episodes])
    assert st2.numbers["guid-a"] == 1 and st2.numbers["guid-0"] == 4


def test_namn_och_titel_som_kafferepet(setup):
    cfg, show, _ = setup
    _, _, wanted = _wanted(cfg, show)
    a = wanted[0]
    # 23:30 GMT 7 nov = 8 nov svensk tid
    assert a.filename == "2025-11-08 - 0001 - Är Joel Halldorf en vampyr Och varför heter alla Emanuel i kyrkan.mp3"
    assert a.fields["title"] == "0001 - Är Joel Halldorf en vampyr? Och varför heter alla Emanuel i kyrkan?"
    assert a.cover_url == "https://bild.example/kanal.jpeg"
    assert wanted[1].cover_url == "https://bild.example/b.jpeg"


def test_filnamn_kortas_till_byte_grans():
    name = naming.filename("2026-01-01", 1, "å" * 300, 4)
    assert len(name.encode()) <= 240 and name.endswith(".mp3")


def test_retag_matchar_flexgets_namn(setup):
    cfg, show, out = setup
    _, _, wanted = _wanted(cfg, show)
    # Flexget: '?' borttaget, mellanslag kvar före .mp3, datum i UTC (7 nov)
    _mp3(out / "2025-11-07 - Är Joel Halldorf en vampyr Och varför heter alla Emanuel i kyrkan .mp3")
    _mp3(out / "2026-07-02 - Torsdagsdeppens stora gräv.mp3")
    by_guid, untagged, probs = plan.scan(out)
    p = plan.build(wanted, by_guid, untagged, match_untagged=True)
    assert probs == [] and p.problems == []
    kinds = sorted((a.kind, a.desired.episode.guid) for a in p.actions)
    assert kinds == [("hamta", "guid-c"), ("tagga", "guid-a"), ("tagga", "guid-b")]


def test_hamta_vagrar_otaggade_filer(setup):
    cfg, show, out = setup
    _, _, wanted = _wanted(cfg, show)
    _mp3(out / "2026-07-02 - Torsdagsdeppens stora gräv.mp3")
    by_guid, untagged, _ = plan.scan(out)
    p = plan.build(wanted, by_guid, untagged, match_untagged=False)
    assert p.problems and "retag" in p.problems[0]


def test_retag_avbryter_vid_tvetydig_match(setup):
    cfg, show, out = setup
    _, _, wanted = _wanted(cfg, show)
    _mp3(out / "2026-07-02 - Torsdagsdeppens stora gräv.mp3")
    _mp3(out / "2026-07-03 - Torsdagsdeppens stora gräv.mp3")
    _mp3(out / "2026-05-01 - Okänt avsnitt.mp3")
    by_guid, untagged, _ = plan.scan(out)
    p = plan.build(wanted, by_guid, untagged, match_untagged=True)
    assert len(p.problems) == 2 and p.actions == []


def test_retag_skriver_taggar_byter_namn_och_ar_idempotent(setup, monkeypatch):
    cfg, show, out = setup
    monkeypatch.setattr(execute.cover, "jpeg", lambda *a, **k: b"\xff\xd8bild")
    _, _, wanted = _wanted(cfg, show)
    old = _mp3(out / "2026-07-02 - Torsdagsdeppens stora gräv.mp3")
    by_guid, untagged, _ = plan.scan(out)
    p = plan.build(wanted, by_guid, untagged, match_untagged=True)
    done, failed = execute.run(p, show, cfg, allow_download=False)
    assert (done, failed) == (1, 0)
    new = out / "2026-07-02 - 0002 - Torsdagsdeppens stora gräv.mp3"
    assert not old.exists() and new.exists()
    assert not [x for x in out.iterdir() if x.name.startswith(".")]
    t = ID3(new)
    assert str(t["TIT2"]) == "0002 - Torsdagsdeppens stora gräv"
    assert str(t["TRCK"]) == "2" and str(t["TDRC"]) == "2026-07-02"
    assert str(t["TALB"]) == "Torsdagsdeppen" and str(t["TPE1"]) == "Kyrkans Tidning"
    assert t.getall("APIC")[0].data == b"\xff\xd8bild" and "TPE2" not in t
    assert tagging.read_ids(new)[0] == "guid-b"
    by_guid, untagged, _ = plan.scan(out)
    p2 = plan.build(wanted, by_guid, untagged, match_untagged=False)
    assert p2.problems == [] and p2.ok == 1
    assert [a.kind for a in p2.actions] == ["hamta", "hamta"]


def test_cli_hamta_avbryter_med_exitkod_1_vid_otaggad_fil(setup, monkeypatch, tmp_path):
    cfg, show, out = setup
    monkeypatch.setattr(cli.feed, "fetch", lambda *a, **k: FEED_XML)
    monkeypatch.setattr(cli.config, "load", lambda _p: cfg)
    _mp3(out / "2026-07-02 - Torsdagsdeppens stora gräv.mp3")
    assert cli.main(["--config", "x", "hamta"]) == 1
    assert (out / "2026-07-02 - Torsdagsdeppens stora gräv.mp3").exists()
    assert cli.main(["--config", "x", "retag"]) == 0  # torrkörning ändrar inget
    assert (out / "2026-07-02 - Torsdagsdeppens stora gräv.mp3").exists()
    assert not (out / "cover.jpg").exists()


def test_cli_hamta_spärrar_utan_state_och_utan_mapp(setup, monkeypatch):
    cfg, show, out = setup
    monkeypatch.setattr(cli.feed, "fetch", lambda *a, **k: FEED_XML)
    monkeypatch.setattr(cli.config, "load", lambda _p: cfg)
    hamtade = []
    monkeypatch.setattr(execute, "_download", lambda url, *a: hamtade.append(url))
    # Tom mapp utan state: utan spärren skulle alla tre avsnitt hämtas.
    assert cli.main(["--config", "x", "hamta"]) == 1 and hamtade == []
    out.rmdir()
    assert cli.main(["--config", "x", "retag", "--apply"]) == 1
    assert not out.exists() and not (cfg.state_dir / "t.json").exists()


def test_retag_apply_pa_tom_mapp_skapar_state_sa_hamta_far_kora(setup, monkeypatch):
    cfg, show, out = setup
    monkeypatch.setattr(cli.feed, "fetch", lambda *a, **k: FEED_XML)
    monkeypatch.setattr(cli.config, "load", lambda _p: cfg)
    monkeypatch.setattr(execute.cover, "jpeg", lambda *a, **k: b"\xff\xd8")
    assert cli.main(["--config", "x", "retag", "--apply"]) == 0
    assert (cfg.state_dir / "t.json").exists()
    hamtade = []
    monkeypatch.setattr(execute, "_download", lambda url, part, ua: (hamtade.append(url), shutil.copyfile(DATA / "tyst.mp3", part)))
    assert cli.main(["--config", "x", "hamta", "--limit", "1"]) == 0
    assert hamtade == ["https://ljud.example/a.mp3"]
