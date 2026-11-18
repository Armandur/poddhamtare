"""Körningar av run.py, en i taget. Loggen strömmas till webbläsaren (SSE) och
sparas per körning i STATE_DIR/runs/<id>.json, även för schemats körningar."""
import asyncio
import json
import logging
import os
import re
import sys
from collections import deque
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
KEEP_RUNS = 100
MAX_LINES = 5000
_RUN_ID = re.compile(r"^\d{8}-\d{6}(-\d+)?$")
# Räknas ur loggraderna så att historiken kan markera körningar med fel.
_COUNTS = {"hamtade": " HÄMTAD ", "taggade": " TAGGAD ", "fel": " FEL ", "problem": " PROBLEM "}


class Broadcaster:
    """Pub/sub för SSE, med en rullande historik så att en nyöppnad flik ser
    loggen från en pågående körning."""

    def __init__(self, history_size=500):
        self.subscribers: set[asyncio.Queue] = set()
        self.history: deque = deque(maxlen=history_size)

    def subscribe(self):
        q: asyncio.Queue = asyncio.Queue()
        for msg in self.history:
            q.put_nowait(msg)
        self.subscribers.add(q)
        return q

    def unsubscribe(self, q):
        self.subscribers.discard(q)

    def publish(self, msg):
        self.history.append(msg)
        for q in self.subscribers:
            q.put_nowait(msg)


class Runner:
    def __init__(self, broadcaster, state_dir, config_path):
        self.broadcaster = broadcaster
        self.runs_dir = Path(state_dir) / "runs"
        self.base_cmd = [sys.executable, "run.py", "--config", str(config_path)]
        self.current: dict | None = None
        self.on_end = []
        self._proc = None
        self._task: asyncio.Task | None = None

    def busy(self):
        return self._task is not None and not self._task.done()

    def start(self, args, trigger):
        """-> körningens metadata, eller None om en körning redan pågår."""
        if self.busy():
            return None
        run = {"id": self._new_id(), "trigger": trigger, "args": list(args),
               "started": datetime.now().isoformat(timespec="seconds")}
        self.current = run
        self._task = asyncio.create_task(self._run(run))
        return run

    async def shutdown(self, timeout=10.0):
        """Vid containerstopp: SIGTERM till run.py, som städar sin .part-fil."""
        if self._proc is not None and self._proc.returncode is None:
            self._proc.terminate()
        if self._task is not None:
            try:
                await asyncio.wait_for(asyncio.shield(self._task), timeout)
            except asyncio.TimeoutError:
                log.warning("run.py avslutades inte inom %.0f s, dödar den", timeout)
                if self._proc is not None:
                    self._proc.kill()
                await self._task

    async def _run(self, run):
        self.broadcaster.history.clear()
        self.broadcaster.publish({"event": "start", **run})
        lines, code = [], None
        try:
            self._proc = await asyncio.create_subprocess_exec(
                *self.base_cmd, *run["args"], cwd=str(PROJECT_ROOT),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
            async for raw in self._proc.stdout:
                line = raw.decode("utf-8", "replace").rstrip()
                if len(lines) < MAX_LINES:
                    lines.append(line)
                print(line, flush=True)  # även till containerloggen i Unraid
                self.broadcaster.publish({"event": "log", "line": line})
            code = await self._proc.wait()
        except Exception as exc:
            log.exception("Körningen kunde inte startas")
            line = f"FEL     Körningen kunde inte startas: {exc}"
            lines.append(line)
            self.broadcaster.publish({"event": "log", "line": line})
        finally:
            self._proc = None
            run.update(ended=datetime.now().isoformat(timespec="seconds"),
                       exit_code=code, lines=lines,
                       **{k: sum(m in f" {ln} " for ln in lines) for k, m in _COUNTS.items()})
            self._save(run)
            self.current = None
            self.broadcaster.publish({"event": "end", "id": run["id"], "exit_code": code})
            for cb in self.on_end:
                cb()

    def _new_id(self):
        base = datetime.now().strftime("%Y%m%d-%H%M%S")
        rid, n = base, 1
        while (self.runs_dir / f"{rid}.json").exists():
            n += 1
            rid = f"{base}-{n}"
        return rid

    def _save(self, run):
        try:
            self.runs_dir.mkdir(parents=True, exist_ok=True)
            tmp = self.runs_dir / f".{run['id']}.tmp"
            tmp.write_text(json.dumps(run, ensure_ascii=False), "utf-8")
            os.replace(tmp, self.runs_dir / f"{run['id']}.json")
            for old in sorted(self.runs_dir.glob("*.json"))[:-KEEP_RUNS]:
                old.unlink()
        except OSError:
            log.exception("Kunde inte spara körningen %s", run["id"])


def list_runs(state_dir):
    """Sammanfattningar, nyast först, utan loggrader."""
    out = []
    runs_dir = Path(state_dir) / "runs"
    for f in sorted(runs_dir.glob("*.json"), reverse=True) if runs_dir.is_dir() else []:
        try:
            run = json.loads(f.read_text("utf-8"))
        except (OSError, ValueError):
            log.warning("Trasig körningsfil hoppas över: %s", f.name)
            continue
        run.pop("lines", None)
        out.append(run)
    return out


def get_run(state_dir, run_id):
    if not _RUN_ID.match(run_id):
        return None
    path = Path(state_dir) / "runs" / f"{run_id}.json"
    return json.loads(path.read_text("utf-8")) if path.is_file() else None
