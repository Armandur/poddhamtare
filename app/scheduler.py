"""Startar 'run.py hamta' enligt CRON_SCHEDULE, via samma Runner som knappen
'Kör nu', så att schemats körningar hamnar i historiken."""
import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from croniter import croniter

log = logging.getLogger(__name__)


class Scheduler:
    def __init__(self, runner, expr, tz_name):
        self.runner = runner
        self.expr = expr
        self.tz = ZoneInfo(tz_name)
        croniter(expr)  # ogiltigt schema ska stoppa starten, inte tystna
        self.next_run: datetime | None = None
        self._task: asyncio.Task | None = None

    def start(self):
        self._task = asyncio.create_task(self._loop())
        log.info("Schema %r, tidszon %s", self.expr, self.tz)

    async def stop(self):
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self):
        while True:
            now = datetime.now(self.tz)
            self.next_run = croniter(self.expr, now).get_next(datetime)
            log.info("Nästa körning %s", self.next_run.strftime("%Y-%m-%d %H:%M"))
            await asyncio.sleep(max(0.0, (self.next_run - datetime.now(self.tz)).total_seconds()))
            if self.runner.start(["hamta"], "schema") is None:
                log.warning("En körning pågår redan, hoppar över den schemalagda")
            await asyncio.sleep(1)
