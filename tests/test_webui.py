import shutil
import sys
import time

import pytest
from fastapi.testclient import TestClient

import run as cli
from app import main as webapp
from hamtare import config, execute, feed
from test_hamtare import DATA, FEED_XML, _mp3

FAKE = "import sys; print('2026-01-01 10:00:00 HÄMTAD  a.mp3'); print('args', *sys.argv[1:])"


@pytest.fixture
def web(tmp_path, monkeypatch):
    out = tmp_path / "podd"
    out.mkdir()
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "shows:\n"
        f"  - name: T\n    slug: t\n    feed_url: https://x\n    output_dir: {out}\n"
        "    album: Torsdagsdeppen\n    artist: Kyrkans Tidning\n", "utf-8")
    monkeypatch.setenv("CONFIG_PATH", str(cfg_file))
    monkeypatch.setenv("STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("CRON_SCHEDULE", "0 0 1 1 *")
    monkeypatch.setattr(feed, "fetch", lambda *a, **k: FEED_XML)
    with TestClient(webapp.app) as client:
        client.app.state.runner.base_cmd = [sys.executable, "-c", FAKE]
        yield client, cfg_file, out


def _wait_for_runs(client, n, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        runs = client.get("/api/runs").json()["runs"]
        if len(runs) >= n and not client.get("/api/status").json()["running"]:
            return runs
        time.sleep(0.05)
    raise AssertionError("körningen blev aldrig klar")


def test_startsidan_och_status(web):
    client, _, _ = web
    r = client.get("/")
    assert r.status_code == 200 and "poddhamtare" in r.text and "/static/app.js?v=" in r.text
    s = client.get("/api/status").json()
    assert s["running"] is False and s["schedule"] == "0 0 1 1 *" and s["next_run"]


def test_kor_nu_sparar_logg_och_raknar(web):
    client, _, _ = web
    r = client.post("/api/run", json={"kind": "hamta", "dry_run": True})
    assert r.status_code == 200
    runs = _wait_for_runs(client, 1)
    assert runs[0]["trigger"] == "manuell" and runs[0]["exit_code"] == 0
    assert runs[0]["hamtade"] == 1 and "lines" not in runs[0]
    full = client.get(f"/api/runs/{runs[0]['id']}").json()
    assert full["lines"][-1] == "args hamta --dry-run"


def test_kor_nu_kraver_json_och_kand_korning(web):
    client, _, _ = web
    assert client.post("/api/run", data={"kind": "hamta"}).status_code == 415
    # Skarp omtaggning går inte att starta från webben.
    assert client.post("/api/run", json={"kind": "retag", "dry_run": False}).status_code == 400
    assert client.post("/api/run", json=["x"]).status_code == 400
    assert client.get("/api/runs").json()["runs"] == []


def test_okand_eller_felaktig_korning_ger_404(web):
    client, _, _ = web
    assert client.get("/api/runs/20260101-000000").status_code == 404
    assert client.get("/api/runs/..%2F..%2Fconfig").status_code == 404


def test_avsnitt_visar_status_utan_att_skriva_state(web, monkeypatch):
    client, cfg_file, out = web
    assert client.get("/api/episodes").json()["shows"][0]["error"].startswith("Ingen state")
    # Ta in en gammal fil med retag, som skapar state.
    monkeypatch.setattr(execute.cover, "jpeg", lambda *a, **k: b"\xff\xd8")
    _mp3(out / "2026-07-02 - Torsdagsdeppens stora gräv.mp3")
    assert cli.main(["--config", str(cfg_file), "retag", "--apply"]) == 0
    state = config.load(cfg_file).state_dir / "t.json"
    before = state.read_bytes()
    shutil.copyfile(DATA / "tyst.mp3", out / "otaggad.mp3")
    show = client.get("/api/episodes?refresh=1").json()["shows"][0]
    status = {e["num"]: e["status"] for e in show["episodes"]}
    assert status == {1: "saknas", 2: "klar", 3: "saknas"}
    assert show["problems"] == ["1 mp3-filer saknar guid-tagg."]
    assert state.read_bytes() == before


def test_avstangning_stoppar_pagaende_korning(tmp_path, web):
    client, _, _ = web
    runner = client.app.state.runner
    runner.base_cmd = [sys.executable, "-c", "import time; print('sover', flush=True); time.sleep(60)"]
    assert client.post("/api/run", json={"kind": "hamta"}).status_code == 200
    assert client.post("/api/run", json={"kind": "hamta"}).status_code == 409
    end = time.time() + 5
    while runner._proc is None and time.time() < end:
        time.sleep(0.02)
    t = time.time()
    client.__exit__(None, None, None)  # kör lifespan-avstängningen
    assert time.time() - t < 8
    runs = list((tmp_path / "state" / "runs").glob("*.json"))
    assert len(runs) == 1 and '"exit_code": -15' in runs[0].read_text("utf-8")
