"""Pipeline stages: discover -> prepare -> apply (auto, verified) -> assist (you submit) -> digest."""
from __future__ import annotations

import logging
import random
import re
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from src.apply import ats as ats_mod
from src.apply.answers import Answers
from src.apply.submitter import ADAPTERS, Submitter, _body
from src.content.cover_letter import CoverLetterWriter, save_letter
from src.content.profile import Profile, cv_text
from src.core.config import Settings, load_yaml
from src.core.models import Job, Status
from src.core.tracker import Tracker, row_list
from src.jobs.filter import JobFilter
from src.jobs.scorer import Scorer
from src.jobs.sources.aggregators import AdzunaSource, ReedSource, RemotiveSource
from src.jobs.sources.ats_boards import AshbySource, GreenhouseSource, LeverSource
from src.jobs.sources.base import SourceError
from src.jobs.sources.remote_boards import (ArbeitnowSource, HimalayasSource, JobicySource, JoobleSource,
                                            RemoteOKSource, WeWorkRemotelySource, WorkingNomadsSource)

log = logging.getLogger("pipeline")


class GateError(RuntimeError):
    """Raised when it is not safe to submit anything yet."""


def _safe(key: str) -> str:
    return re.sub(r"[^\w.-]+", "_", key)


def row_to_job(r) -> Job:
    return Job(source=r["source"], source_id=r["source_id"], title=r["title"], company=r["company"],
               location=r["location"] or "", description=r["description"] or "", url=r["url"] or "",
               apply_url=r["apply_url"], salary=r["salary"], work_type=r["work_type"] or "Unspecified")


class Pipeline:
    def __init__(self, settings: Settings, tracker: Tracker, profile: Profile,
                 sources_cfg: Optional[dict] = None, filter_cfg: Optional[dict] = None,
                 answers_cfg: Optional[dict] = None, notifier=None):
        from src.notify.discord import NullNotifier
        self.notify = notifier or NullNotifier()
        self.flagged: list[str] = []          # keys sent to needs_manual/failed during this run
        self.s = settings
        self.t = tracker
        self.profile = profile
        self.src_cfg = sources_cfg if sources_cfg is not None else load_yaml("sources.yaml")
        self.filter = JobFilter(filter_cfg)
        self.answers_cfg = answers_cfg if answers_cfg is not None else load_yaml("answers.yaml")
        vocab = (filter_cfg or load_yaml("filters.yaml")).get("skills", [])
        self.scorer = Scorer(cv_text(settings.cv_path, profile), profile.skills, vocab)

    # ================================================================== 1. discover
    def build_sources(self) -> list:
        c = self.src_cfg
        out = []
        searches = c.get("searches", [])
        if c.get("reed", {}).get("enabled", True):
            out.append(ReedSource(searches))
        if c.get("adzuna", {}).get("enabled", True):
            out.append(AdzunaSource(searches, pages=c.get("adzuna", {}).get("pages", 2)))
        if c.get("jooble", {}).get("enabled", True):
            out.append(JoobleSource(searches))
        # worldwide remote boards
        remote = {"remotive": RemotiveSource, "remoteok": RemoteOKSource, "himalayas": HimalayasSource,
                  "jobicy": JobicySource, "workingnomads": WorkingNomadsSource,
                  "weworkremotely": WeWorkRemotelySource, "arbeitnow": ArbeitnowSource}
        for name, cls in remote.items():
            if c.get(name, {}).get("enabled", True):
                out.append(cls())
        gh = sorted(set(c.get("greenhouse_boards", []) + self.t.boards("greenhouse")))
        lv = sorted(set(c.get("lever_sites", []) + self.t.boards("lever")))
        ab = sorted(set(c.get("ashby_orgs", []) + self.t.boards("ashby")))
        if gh:
            out.append(GreenhouseSource(gh))
        if lv:
            out.append(LeverSource(lv))
        if ab:
            out.append(AshbySource(ab))
        return out

    def discover(self, sources: Optional[list] = None) -> dict:
        stats = {"fetched": 0, "new": 0, "duplicates": 0, "filtered_out": 0, "shortlisted": 0, "errors": []}
        for src in sources if sources is not None else self.build_sources():
            name = getattr(src, "name", src.__class__.__name__)
            log.info("fetching %s ...", name)
            try:
                jobs = src.fetch()
            except Exception as e:   # one broken source never stops the run
                stats["errors"].append(f"{getattr(src, 'name', src)}: {e}")
                log.error("%s: %s", getattr(src, "name", src), e)
                continue
            stats["fetched"] += len(jobs)
            for job in jobs:
                if not job.title or not job.url:
                    continue
                if self.t.seen(job):
                    stats["duplicates"] += 1
                    continue
                pre = self.filter.title_ok(job)
                if pre.accepted and hasattr(src, "enrich"):
                    job = src.enrich(job)
                self.t.add_found(job)
                stats["new"] += 1
                res = self.filter.evaluate(job) if pre.accepted else pre
                if not res.accepted:
                    self.t.set_status(job.key, Status.FILTERED_OUT, res.reason)
                    stats["filtered_out"] += 1
                    continue
                sc = self.scorer.score(job.title + " " + job.description)
                self.t.update_fields(job.key, score=sc.value, matched_skills=sc.have, missing_skills=sc.missing)
                if sc.value < self.s.min_score:
                    self.t.set_status(job.key, Status.FILTERED_OUT, f"relevance {sc.value:.2f} < {self.s.min_score}")
                    stats["filtered_out"] += 1
                    continue
                self._route(job)
                self.t.set_status(job.key, Status.SHORTLISTED, f"relevance {sc.value:.2f}")
                stats["shortlisted"] += 1
        if stats["errors"]:
            self.notify.error("Some job sources failed this run:\n" + "\n".join(f"• {e}" for e in stats["errors"]))
        log.info("discover: %s", stats)
        return stats

    def _route(self, job: Job) -> None:
        """Find out where the application form lives; remember any ATS boards we discover."""
        target = ats_mod.detect(job.apply_url or job.url)
        if target.ats not in ats_mod.AUTO_SUPPORTED and job.apply_url and job.source not in ats_mod.AUTO_SUPPORTED:
            target = ats_mod.resolve(job.apply_url)
        if target.ats in ats_mod.AUTO_SUPPORTED and target.token:
            if self.t.add_board(target.ats, target.token, job.company, job.key):
                log.info("discovered new %s board: %s (%s)", target.ats, target.token, job.company)
        self.t.update_fields(job.key, ats=target.ats, apply_url=target.form_url or job.apply_url or job.url)

    # ================================================================== 2. prepare
    def prepare(self, limit: int = 40, use_llm: bool = True) -> int:
        writer = CoverLetterWriter(self.profile, self.s.llm_model, use_llm)
        n = 0
        for r in self.t.by_status(Status.SHORTLISTED)[:limit]:
            job = row_to_job(r)
            letter = writer.write(job, row_list(r, "matched_skills"))
            notes = "; ".join(letter.guard_notes)
            self.t.update_fields(job.key, cover_letter=letter.text, notes=notes or None)
            if r["ats"] in ats_mod.AUTO_SUPPORTED:
                self.t.set_status(job.key, Status.READY, f"cover letter ({letter.method}); auto-submit via {r['ats']}")
            else:
                self.t.set_status(job.key, Status.NEEDS_MANUAL,
                                  f"{r['ats'] or 'site'} has no reliable auto-apply — submit in assist mode")
                self.flagged.append(job.key)
            n += 1
        return n

    # ================================================================== 3. auto-apply
    def check_gates(self, dry_run: bool = False) -> None:
        problems = []
        if not self.s.profile_reviewed and not dry_run:
            problems.append("config/settings.yaml: set profile_reviewed: true after checking config/user_profile.yaml "
                            "and config/answers.yaml are accurate")
        if not self.s.cv_path or not self.s.cv_path.exists():
            problems.append(f"CV not found at '{self.s.cv_path}' — set cv_path in settings.yaml (PDF)")
        if problems:
            raise GateError("Not submitting anything until fixed:\n  - " + "\n  - ".join(problems))

    @contextmanager
    def browser(self, headless: Optional[bool] = None) -> Iterator:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            ctx = pw.chromium.launch_persistent_context(
                str(self.s.browser_profile), headless=self.s.headless if headless is None else headless,
                locale="en-GB", timezone_id="Europe/London", viewport={"width": 1280, "height": 900})
            try:
                yield ctx
            finally:
                ctx.close()

    def apply(self, dry_run: bool = False, limit: Optional[int] = None, context=None) -> dict:
        self.check_gates(dry_run)
        remaining = self.s.daily_cap - self.t.count_applied_today()
        if limit is not None:
            remaining = min(remaining, limit)
        stats = {s.value: 0 for s in Status}
        if remaining <= 0:
            log.info("daily cap of %d verified applications reached", self.s.daily_cap)
            return stats
        queue = [r for r in self.t.by_status(Status.READY) if r["ats"] in ADAPTERS][:remaining]
        if not queue:
            return stats

        def run(ctx):
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            for i, r in enumerate(queue):
                outcome = self.apply_one(r, page, dry_run)
                stats[outcome.status.value] += 1
                if i < len(queue) - 1 and not dry_run:
                    time.sleep(random.uniform(*self.s.delay_seconds))

        if context is not None:
            run(context)
        else:
            with self.browser() as ctx:
                run(ctx)
        log.info("apply: %s", {k: v for k, v in stats.items() if v})
        return stats

    def apply_one(self, r, page, dry_run: bool = False):
        job = row_to_job(r)
        ev = self.s.evidence_dir / _safe(job.key)
        cl_path = save_letter(r["cover_letter"] or "", ev)
        answers = Answers(self.answers_cfg, self.profile, r["cover_letter"] or "")
        sub = Submitter(page, r["ats"], answers, self.s.cv_path, cl_path, ev, self.s.confirm_timeout_s)
        log.info("applying: %s — %s (%s)", job.title, job.company, r["apply_url"])
        out = sub.apply(r["apply_url"], dry_run=dry_run)
        if out.status == Status.APPLIED:
            self.t.set_status(job.key, Status.APPLIED, out.detail, confirmation_text=out.confirmation_text,
                              method="auto", evidence_dir=out.evidence_dir, follow_up_days=self.s.follow_up_days)
            self.notify.applied(self.t.get(job.key))
            self.interview_prep(job.key)
        else:
            self.t.set_status(job.key, out.status, out.detail, evidence_dir=out.evidence_dir,
                              unanswered=out.unanswered or None)
            if out.status == Status.FAILED:
                self.notify.failed(self.t.get(job.key))
            elif out.status == Status.NEEDS_MANUAL:
                self.flagged.append(job.key)
        log.info("  -> %s: %s%s", out.status.value, out.detail,
                 ("\n     " + "\n     ".join(out.unanswered)) if out.unanswered else "")
        return out

    def notify_run_end(self, discover_stats: Optional[dict] = None, apply_stats: Optional[dict] = None) -> None:
        """Send the 'could not auto-apply' list for this run and a summary."""
        from src.notify.digest import breakdown, why_bucket
        rows = [r for k in dict.fromkeys(self.flagged) if (r := self.t.get(k)) is not None
                and r["status"] in (Status.NEEDS_MANUAL.value,)]
        self.notify.needs_you(rows, why_bucket)
        d = discover_stats or {}
        a = apply_stats or {}
        stats = {"New jobs found": d.get("new", 0), "Shortlisted": d.get("shortlisted", 0),
                 "Applied today (verified)": self.t.count_applied_today(),
                 "Applied this run": a.get("applied", 0), "Failed": a.get("failed", 0),
                 "Waiting for you (total)": len(self.t.by_status(Status.NEEDS_MANUAL, Status.FAILED))}
        self.notify.summary(stats, breakdown(self.t.by_status(Status.NEEDS_MANUAL, Status.FAILED)))

    def interview_prep(self, key: str) -> Optional[Path]:
        """Write the prep guide for a job and announce it on Discord."""
        from src.content import interview_prep as ip
        if not self.s.raw.get("interview_prep", {}).get("enabled", True):
            return None
        r = self.t.get(key)
        if r is None:
            return None
        have, missing = row_list(r, "matched_skills"), row_list(r, "missing_skills")
        out = self.s.evidence_dir.parent / "interview_prep"
        info = ip.maybe(r, self.profile, out, have, missing)
        if info:
            self.notify.interview_prep(info, ip.topics_for(have + missing))
            return Path(info["path"])
        return None

    # ================================================================== 4. assist (you click submit)
    def assist(self, limit: int = 20, prompt=input) -> dict:
        """Opens each NEEDS_MANUAL / FAILED job, pre-fills what it can, and waits for YOU to submit.
        Marked APPLIED only when the ATS confirmation is seen or you type 'a'."""
        self.check_gates()
        queue = self.t.by_status(Status.NEEDS_MANUAL, Status.FAILED)[:limit]
        stats = {"applied": 0, "skipped": 0, "later": 0}
        if not queue:
            print("Nothing waiting for you.")
            return stats
        with self.browser(headless=False) as ctx:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            for n, r in enumerate(queue, 1):
                job = row_to_job(r)
                ev = self.s.evidence_dir / _safe(job.key)
                ev.mkdir(parents=True, exist_ok=True)
                print(f"\n[{n}/{len(queue)}] {job.title} — {job.company}  ({r['ats']}, score {r['score'] or 0:.2f})")
                print(f"  why manual: {r['reason']}")
                for q in row_list(r, "unanswered"):
                    print(f"  • {q}")
                if r["cover_letter"]:
                    cl = save_letter(r["cover_letter"], ev)
                    print(f"  cover letter: {cl}")
                url = r["apply_url"] or r["url"]
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=45000)
                except Exception as e:
                    print(f"  could not open page: {e}")
                if r["ats"] in ADAPTERS:
                    self._prefill(page, r, ev)
                    print("  Form pre-filled where answers are configured. Check it, answer the rest, submit.")
                else:
                    print("  Apply on this page (log in if needed), then come back here.")
                while True:
                    ans = prompt("  [a] I submitted it   [s] skip (not applying)   [l] later   [q] quit > ").strip().lower()
                    if ans in ("a", "s", "l", "q"):
                        break
                if ans == "q":
                    break
                if ans == "l":
                    stats["later"] += 1
                    continue
                if ans == "s":
                    self.t.set_status(job.key, Status.SKIPPED, "skipped in assist mode")
                    stats["skipped"] += 1
                    continue
                body = _body(page)
                ad = ADAPTERS.get(r["ats"])
                seen = bool(ad and (ad.success_text.search(body) or ad.success_url.search(page.url)))
                try:
                    page.screenshot(path=str(ev / "assist_after_submit.png"), full_page=True)
                except Exception:
                    pass
                (ev / "assist_page.txt").write_text(f"URL: {page.url}\n\n{body[:4000]}", encoding="utf-8")
                self.t.set_status(job.key, Status.APPLIED,
                                  "confirmation detected" if seen else "you confirmed submission",
                                  confirmation_text=(body[:200] if seen else None), method="user_confirmed",
                                  evidence_dir=str(ev), follow_up_days=self.s.follow_up_days)
                self.notify.applied(self.t.get(job.key))
                self.interview_prep(job.key)
                stats["applied"] += 1
        return stats

    def _prefill(self, page, r, ev: Path) -> None:
        from src.apply.form_engine import FormEngine
        try:
            ad = ADAPTERS[r["ats"]]
            if ad.open_form:
                b = page.locator(ad.open_form).first
                if b.is_visible(timeout=1500):
                    b.click()
            page.wait_for_selector(ad.ready, timeout=10000)
            eng = FormEngine(page, Answers(self.answers_cfg, self.profile, r["cover_letter"] or ""),
                             self.s.cv_path, save_letter(r["cover_letter"] or "", ev))
            plan = eng.plan()
            eng.fill(plan)
        except Exception as e:
            log.debug("prefill failed: %s", e)
