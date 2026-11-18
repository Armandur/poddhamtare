"""Webbgränssnittet: status, Kör nu, avsnittslista, körningshistorik och livelogg."""
import asyncio
import hashlib
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import episodes, jobs
from app.scheduler import Scheduler
from hamtare import config

BASE = Path(__file__).parent
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S", stream=sys.stdout)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Knappen får bara starta dessa. Skarp omtaggning görs inte från webben.
_COMMANDS = {
    ("hamta", False): ["hamta"],
    ("hamta", True): ["hamta", "--dry-run"],
    ("retag", True): ["retag"],
}


def _static_version():
    h = hashlib.sha1()
    for f in sorted((BASE / "static").iterdir()):
        h.update(f.read_bytes())
    return h.hexdigest()[:8]


@asynccontextmanager
async def lifespan(app: FastAPI):
    config_path = os.environ.get("CONFIG_PATH", "config.yaml")
    cfg = config.load(config_path)
    app.state.config_path = config_path
    app.state.state_dir = cfg.state_dir
    app.state.broadcaster = jobs.Broadcaster()
    app.state.runner = jobs.Runner(app.state.broadcaster, cfg.state_dir, config_path)
    app.state.episodes = episodes.Cache(lambda: episodes.overview(config.load(config_path)))
    app.state.runner.on_end.append(app.state.episodes.invalidate)
    app.state.scheduler = Scheduler(app.state.runner,
                                    os.environ.get("CRON_SCHEDULE", "30 */3 * * *"),
                                    os.environ.get("TZ", "Europe/Stockholm"))
    app.state.scheduler.start()
    try:
        yield
    finally:
        await app.state.scheduler.stop()
        await app.state.runner.shutdown()


app = FastAPI(title="poddhamtare", lifespan=lifespan, docs_url=None, redoc_url=None)
templates = Jinja2Templates(directory=BASE / "templates")
templates.env.globals["static_v"] = _static_version()
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")


@app.get("/")
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {})


@app.get("/api/status")
def status(request: Request):
    s = request.app.state
    return {"running": s.runner.busy(), "current": s.runner.current,
            "schedule": s.scheduler.expr,
            "next_run": s.scheduler.next_run.isoformat() if s.scheduler.next_run else None}


@app.get("/api/episodes")
def get_episodes(request: Request, refresh: int = 0):
    data, at = request.app.state.episodes.get(refresh=bool(refresh))
    return {"shows": data, "fetched_at": at}


@app.get("/api/runs")
def runs(request: Request):
    return {"runs": jobs.list_runs(request.app.state.state_dir)}


@app.get("/api/runs/{run_id}")
def run_detail(request: Request, run_id: str):
    run = jobs.get_run(request.app.state.state_dir, run_id)
    if run is None:
        return JSONResponse({"error": "Körningen finns inte."}, status_code=404)
    return run


@app.post("/api/run")
async def start_run(request: Request):
    # Kräver JSON: ett formulär på en annan sajt kan då inte starta en körning.
    if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
        return JSONResponse({"error": "Förfrågan måste vara JSON."}, status_code=415)
    try:
        body = await request.json()
        args = _COMMANDS[(body.get("kind", "hamta"), bool(body.get("dry_run")))]
    except (ValueError, AttributeError, KeyError, TypeError):
        return JSONResponse({"error": "Okänd körning."}, status_code=400)
    run = request.app.state.runner.start(args, "manuell")
    if run is None:
        return JSONResponse({"error": "En körning pågår redan."}, status_code=409)
    return {"ok": True, "run": run}


@app.get("/api/events")
async def events(request: Request):
    b = request.app.state.broadcaster
    q = b.subscribe()

    async def gen():
        try:
            while not await request.is_disconnected():
                try:
                    msg = await asyncio.wait_for(q.get(), 15)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
        finally:
            b.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
