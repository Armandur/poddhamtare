"""poddhamtare - hämtar poddar ur RSS och taggar filerna ur flödet.

  python run.py hamta [--dry-run] [--limit N]   hämta nya avsnitt, tagga om ändrade
  python run.py retag [--apply]                 matcha gamla filer och tagga om (torrkörning utan --apply)
  python run.py schema                          kör 'hamta' enligt CRON_SCHEDULE
"""
import argparse
import logging
import os
import signal
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from croniter import croniter

from hamtare import config, execute, feed, plan
from hamtare.lock import Lock
from hamtare.state import State

log = logging.getLogger("poddhamtare")


def run_show(show, cfg, *, mode, dry_run, limit=None):
    """-> True om showen gick igenom utan problem eller fel."""
    log.info("== %s ==", show.name)
    state_path = cfg.state_dir / f"{show.slug}.json"
    if not show.output_dir.is_dir():
        log.error("PROBLEM Mappen finns inte: %s. Kontrollera monteringen.", show.output_dir)
        return False
    if mode == "hamta" and not state_path.exists():
        # Spärr: utan state vet vi inte vilka avsnitt som redan finns. Tom mapp
        # efter en felstavad montering skulle annars ge 47 nya hämtningar.
        log.error("PROBLEM Ingen state för %s. Kör 'retag --apply' först.", show.name)
        return False
    f = feed.parse(feed.fetch(show.feed_url, cfg.user_agent))
    state = State(state_path)
    state.assign_numbers(f.episodes)
    wanted = plan.desired(show, cfg, f, state)
    by_guid, untagged, problems = plan.scan(show.output_dir)
    p = plan.build(wanted, by_guid, untagged, match_untagged=(mode == "retag"))
    p.problems[:0] = problems

    for note in p.notes:
        log.info("NOTERA  %s", note)
    for prob in p.problems:
        log.error("PROBLEM %s", prob)
    if p.problems:
        log.error("Avbryter %s: %d problem, inget är ändrat.", show.name, len(p.problems))
        return False

    for a in p.actions:
        d = a.desired
        if a.kind == "hamta":
            log.info("%s %s", "HÄMTA  " if mode == "hamta" else "SAKNAS ", d.filename)
        elif a.src.name != d.filename:
            log.info("TAGGA   %s\n        -> %s", a.src.name, d.filename)
        else:
            log.info("TAGGA   %s", d.filename)
    log.info("%d avsnitt i flödet: %d klara, %d att hämta, %d att tagga om",
             len(wanted), p.ok, sum(a.kind == "hamta" for a in p.actions),
             sum(a.kind == "tagga" for a in p.actions))

    execute.ensure_folder_cover(show, cfg, f, state, dry_run=dry_run)
    if dry_run:
        log.info("Torrkörning: inget är ändrat.")
        return True
    done, failed = execute.run(p, show, cfg, allow_download=(mode == "hamta"), limit=limit)
    state.save()
    log.info("Klart: %d utförda, %d fel", done, failed)
    return failed == 0


def run_all(cfg, **kw):
    ok = True
    with Lock(cfg.state_dir / "run.lock"):
        for show in cfg.shows:
            try:
                ok &= run_show(show, cfg, **kw)
            except Exception:
                log.exception("FEL     %s avbröts", show.name)
                ok = False
    return ok


def schedule(cfg):
    # PID 1 i containern får ingen standardhanterare för SIGTERM. Utan den här
    # väntar 'docker stop' tills timeouten. SystemExit kör finally-blocken,
    # så en halv .part-fil städas bort.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    expr = os.environ.get("CRON_SCHEDULE", "30 */3 * * *")
    tz = ZoneInfo(os.environ.get("TZ", "Europe/Stockholm"))
    log.info("Schema %r, tidszon %s", expr, tz)
    while True:
        nxt = croniter(expr, datetime.now(tz)).get_next(datetime)
        log.info("Nästa körning %s", nxt.strftime("%Y-%m-%d %H:%M"))
        time.sleep(max(0.0, (nxt - datetime.now(tz)).total_seconds()))
        try:
            run_all(cfg, mode="hamta", dry_run=False)
        except BlockingIOError:
            log.warning("En annan körning pågår, hoppar över den här")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Hämtar poddar ur RSS och taggar filerna ur flödet.")
    ap.add_argument("--config", default=os.environ.get("CONFIG_PATH", "config.yaml"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("hamta", help="hämta nya avsnitt och tagga om ändrade")
    h.add_argument("--dry-run", action="store_true")
    h.add_argument("--limit", type=int, help="högst så här många hämtningar per show")
    r = sub.add_parser("retag", help="matcha gamla filer och tagga om dem")
    r.add_argument("--apply", action="store_true", help="utan den blir det en torrkörning")
    sub.add_parser("schema", help="kör 'hamta' enligt CRON_SCHEDULE")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                        datefmt="%Y-%m-%d %H:%M:%S")
    cfg = config.load(args.config)
    if args.cmd == "schema":
        schedule(cfg)
        return 0
    if args.cmd == "hamta":
        ok = run_all(cfg, mode="hamta", dry_run=args.dry_run, limit=args.limit)
    else:
        ok = run_all(cfg, mode="retag", dry_run=not args.apply)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
