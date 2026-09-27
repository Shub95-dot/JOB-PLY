"""job-app-agent — finds UK entry-level data roles, submits verified applications where it can,
and walks you through the rest.

  python main.py run                 discover + prepare + auto-apply (up to daily cap) + digest
  python main.py run --dry-run       same, but fills forms and screenshots WITHOUT clicking submit
  python main.py discover            only fetch/filter/score new postings
  python main.py prepare             write cover letters for shortlisted jobs
  python main.py apply [--dry-run]   submit READY jobs on Greenhouse/Lever/Ashby
  python main.py assist              open each job that needs you; you submit, it records it
  python main.py status              counts + follow-ups due
  python main.py show KEY            full record + event history for one job
  python main.py mark KEY STATUS     e.g. mark reed:5735521 interview   (interview -> writes prep guide)
  python main.py prep KEY            write/refresh the interview-prep guide for one job
  python main.py digest              write today's HTML digest (and email it if SMTP is set)
  python main.py import-legacy FILE  import the old application_tracker.json as UNVERIFIED
  python main.py check-boards        test every Greenhouse/Lever/Ashby token in sources.yaml
  python main.py test-discord        send a test message to your Discord channel
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

from src.content.profile import Profile
from src.core.config import ROOT, Settings, load_env, load_yaml, setup_logging
from src.core.models import Status
from src.core.tracker import Tracker, row_list
from src.notify import digest
from src.pipeline import GateError, Pipeline

log = logging.getLogger("main")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--no-apply", action="store_true", help="discover + prepare only")
    r.add_argument("--no-llm", action="store_true")
    r.add_argument("--limit", type=int)
    sub.add_parser("discover")
    p = sub.add_parser("prepare")
    p.add_argument("--no-llm", action="store_true")
    a = sub.add_parser("apply")
    a.add_argument("--dry-run", action="store_true")
    a.add_argument("--limit", type=int)
    s = sub.add_parser("assist")
    s.add_argument("--limit", type=int, default=20)
    sub.add_parser("status")
    sh = sub.add_parser("show")
    sh.add_argument("key")
    m = sub.add_parser("mark")
    m.add_argument("key")
    m.add_argument("status", choices=[x.value for x in (Status.RESPONDED, Status.INTERVIEW, Status.REJECTED,
                                                        Status.OFFER, Status.SKIPPED, Status.NEEDS_MANUAL)])
    m.add_argument("--note", default="")
    pr = sub.add_parser("prep", help="write the interview-prep guide for one job")
    pr.add_argument("key")
    sub.add_parser("digest")
    il = sub.add_parser("import-legacy")
    il.add_argument("file")
    il.add_argument("--requeue", action="store_true", help="put real postings into the assist queue")
    sub.add_parser("check-boards")
    sub.add_parser("test-discord", help="send a test message to your Discord webhook")
    args = ap.parse_args(argv)

    load_env()
    setup_logging()
    settings = Settings()
    tracker = Tracker(settings.db_path)

    if args.cmd == "status":
        return _status(tracker)
    if args.cmd == "show":
        return _show(tracker, args.key)
    if args.cmd == "mark":
        tracker.set_status(args.key, Status(args.status), args.note or f"marked {args.status}")
        print(f"{args.key} -> {args.status}")
        if args.status == Status.INTERVIEW.value:
            args.cmd = "prep"          # fall through: (re)build the interview guide
        else:
            return 0
    if args.cmd == "import-legacy":
        from src.legacy import import_legacy
        print(import_legacy(Path(args.file), tracker, requeue=args.requeue))
        return 0
    if args.cmd == "digest":
        return _digest(settings, tracker)
    if args.cmd == "check-boards":
        return _check_boards()
    if args.cmd == "test-discord":
        from src.notify.discord import DiscordNotifier
        n = DiscordNotifier((settings.raw.get("notifications") or {}).get("discord"))
        if not n.url:
            print("DISCORD_WEBHOOK_URL is not set in .env")
            return 1
        ok = n.summary({"Test": "Discord notifications are working"}, {})
        print("sent" if ok else "failed — check the webhook URL")
        return 0 if ok else 1

    from src.notify.discord import DiscordNotifier
    notifier = DiscordNotifier((settings.raw.get("notifications") or {}).get("discord"))
    profile = Profile.load()
    pipe = Pipeline(settings, tracker, profile, notifier=notifier)
    try:
        if args.cmd == "prep":
            path = pipe.interview_prep(args.key)
            print(f"interview prep: {path}" if path else "not generated (unknown key or disabled)")
            return 0
        if args.cmd == "discover":
            print(pipe.discover())
        elif args.cmd == "prepare":
            print(f"prepared {pipe.prepare(use_llm=not args.no_llm)} jobs")
        elif args.cmd == "apply":
            res = pipe.apply(dry_run=args.dry_run, limit=args.limit)
            print(res)
        elif args.cmd == "assist":
            print(pipe.assist(limit=args.limit))
        elif args.cmd == "run":
            d = pipe.discover()
            print(d)
            print(f"prepared {pipe.prepare(use_llm=not args.no_llm)} jobs")
            a = {}
            if not args.no_apply:
                try:
                    a = pipe.apply(dry_run=args.dry_run, limit=args.limit)
                    print(a)
                except GateError as e:
                    print(f"\n{e}\n")
            pipe.notify_run_end(d, a)
            _digest(settings, tracker)
    except GateError as e:
        print(f"\n{e}\n")
        return 2
    except Exception as e:
        notifier.error(f"`python main.py {args.cmd}` crashed: {e.__class__.__name__}: {e}")
        raise
    if args.cmd in ("apply", "prepare"):
        pipe.notify_run_end(None, locals().get("res") or {})
    return 0


def _status(t: Tracker) -> int:
    c = t.counts()
    order = [s.value for s in Status]
    print("\nStatus counts")
    for k in order:
        if c.get(k):
            print(f"  {k:<18} {c[k]}")
    print(f"\nVerified applications today: {t.count_applied_today()}")
    due = t.follow_ups_due()
    if due:
        print("\nFollow-ups due:")
        for r in due:
            print(f"  {r['key']:<40} {r['title']} — {r['company']} (applied {r['applied_at'][:10]})")
    blocked = t.by_status(Status.NEEDS_MANUAL, Status.FAILED)
    if blocked:
        from src.notify.digest import breakdown
        print(f"\nCOULD NOT AUTO-APPLY: {len(blocked)} jobs  (finish them with: python main.py assist)")
        for reason, n in breakdown(blocked).items():
            print(f"  {n:>4}  {reason}")
    return 0


def _show(t: Tracker, key: str) -> int:
    r = t.get(key)
    if not r:
        print("not found")
        return 1
    for k in r.keys():
        if k in ("description", "cover_letter"):
            continue
        if r[k]:
            print(f"{k:>18}: {r[k]}")
    if r["cover_letter"]:
        print("\n--- cover letter ---\n" + r["cover_letter"])
    print("\n--- history ---")
    for e in t.events_for(key):
        print(f"{e['ts']}  {e['from_status'] or '-':>14} -> {e['to_status']:<14} {e['detail'] or ''}")
    return 0


def _digest(settings: Settings, t: Tracker) -> int:
    p = digest.save(t, settings.digest_dir)
    applied = t.count_applied_today()
    manual = len(t.by_status(Status.NEEDS_MANUAL))
    digest.email(p.read_text(encoding="utf-8"),
                 f"Jobs {date.today():%d %b}: {applied} applied (verified), {manual} need you")
    print(f"digest: {p}")
    return 0


def _check_boards() -> int:
    from src.jobs.sources.ats_boards import AshbySource, GreenhouseSource, LeverSource
    c = load_yaml("sources.yaml")
    checks = [(GreenhouseSource, "greenhouse_boards"), (LeverSource, "lever_sites"), (AshbySource, "ashby_orgs")]
    for cls, key in checks:
        for token in c.get(key, []):
            try:
                n = len(cls([token]).fetch())
                print(f"  {'OK ' if n else 'EMPTY'} {cls.name:<10} {token:<25} {n} open roles")
            except Exception as e:
                print(f"  ERR {cls.name:<10} {token:<25} {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
