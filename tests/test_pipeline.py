"""Discover -> prepare -> apply, end to end, with a fake source and a local Lever-style form."""
from src.core.models import Job, Status
from src.core.tracker import Tracker
from src.pipeline import GateError, Pipeline
from tests.conftest import FORMS

import pytest


class FakeSource:
    name = "fake"

    def __init__(self, jobs):
        self.jobs = jobs

    def fetch(self):
        return self.jobs


DESC = ("Graduate Data Analyst in London. You will use SQL, Python, Excel and Power BI to build dashboards, "
        "clean data and run exploratory data analysis with statistics. Training and mentoring provided. ") * 3


def jobs():
    lever_url = (FORMS / "lever_form.html").as_uri()
    return [
        Job(source="lever", source_id="acme/1", title="Graduate Data Analyst", company="Acme", location="London, UK",
            description=DESC, url=lever_url, apply_url=lever_url),
        Job(source="reed", source_id="555", title="Junior Data Analyst", company="Delta", location="Southampton",
            description=DESC, url="https://www.reed.co.uk/jobs/junior-data-analyst/555"),
        Job(source="reed", source_id="556", title="Senior Data Analyst", company="Epsilon", location="London",
            description=DESC, url="https://www.reed.co.uk/jobs/senior-data-analyst/556"),
        Job(source="reed", source_id="557", title="Remote Data Entry Clerk", company="Zeta", location="London",
            description=DESC, url="https://www.reed.co.uk/jobs/x/557"),
    ]


def test_end_to_end(settings, profile, answered_cfg, browser, monkeypatch):
    t = Tracker(settings.db_path)
    pipe = Pipeline(settings, t, profile, sources_cfg={}, answers_cfg=answered_cfg)
    # local file:// URL isn't a lever.co URL, so route it manually the way detect() would for a real one
    monkeypatch.setattr(pipe, "_route", lambda job: t.update_fields(
        job.key, ats="lever" if job.source == "lever" else "reed", apply_url=job.apply_url or job.url))
    st = pipe.discover([FakeSource(jobs())])
    assert st["shortlisted"] == 2 and st["filtered_out"] == 2
    assert pipe.prepare(use_llm=False) == 2
    assert t.get("reed:555")["status"] == Status.NEEDS_MANUAL.value
    ctx = browser.new_context()
    res = pipe.apply(context=ctx)
    ctx.close()
    assert res["applied"] == 1
    row = t.get("lever:acme/1")
    assert row["status"] == "applied" and "Application submitted" in row["confirmation_text"]
    # second run: nothing re-applied, no duplicates
    st2 = pipe.discover([FakeSource(jobs())])
    assert st2["new"] == 0 and st2["duplicates"] == 4


def test_gate_blocks_unreviewed_profile(settings, profile):
    settings.profile_reviewed = False
    pipe = Pipeline(settings, Tracker(settings.db_path), profile, sources_cfg={})
    with pytest.raises(GateError):
        pipe.apply()


def test_dry_run_allowed_before_review(settings, profile):
    settings.profile_reviewed = False
    pipe = Pipeline(settings, Tracker(settings.db_path), profile, sources_cfg={})
    assert pipe.apply(dry_run=True)["applied"] == 0      # no GateError; nothing queued


def test_refilter_recovers_jobs_after_rule_change(settings, profile):
    t = Tracker(settings.db_path)
    pipe = Pipeline(settings, t, profile, sources_cfg={})
    job = Job(source="reed", source_id="900", title="Data Analyst (12 Month Contract)", company="Omega",
              location="Southampton", description=DESC, url="https://www.reed.co.uk/jobs/x/900")
    t.add_found(job)
    t.set_status(job.key, Status.FILTERED_OUT, "seniority/unsuitable word 'contract' in title")
    pipe._route = lambda j: t.update_fields(j.key, ats="reed", apply_url=j.url)
    assert pipe.refilter()["now_shortlisted"] == 1
    assert t.get(job.key)["status"] == "shortlisted"


def test_assist_writes_letter_for_legacy_jobs(settings, profile, monkeypatch):
    from contextlib import contextmanager
    t = Tracker(settings.db_path)
    pipe = Pipeline(settings, t, profile, sources_cfg={})
    job = Job(source="legacy", source_id="https://x/1", title="Data Analyst", company="KP Law", url="https://x/1")
    t.add_found(job)
    t.set_status(job.key, Status.NEEDS_MANUAL, "from old tool")

    class P:
        url = "about:blank"
        def goto(self, *a, **k): pass
        def inner_text(self, *a, **k): return ""
        def screenshot(self, *a, **k): pass

    class C:
        pages = [P()]

    @contextmanager
    def fake_browser(headless=None):
        yield C()
    monkeypatch.setattr(pipe, "browser", fake_browser)
    opened = []
    pipe.assist(prompt=lambda _: "l", open_normal=opened.append)
    assert opened == ["https://x/1"]            # non-ATS jobs open in the normal browser
    row = t.get(job.key)
    assert row["cover_letter"] and "KP Law" in row["cover_letter"]
    assert list(settings.evidence_dir.glob("*/cover_letter.txt"))



def test_assist_normal_browser_submit_is_recorded(settings, profile):
    t = Tracker(settings.db_path)
    pipe = Pipeline(settings, t, profile, sources_cfg={})
    job = Job(source="reed", source_id="77", title="Junior Data Analyst", company="Delta",
              description=DESC, url="https://www.reed.co.uk/jobs/x/77")
    t.add_found(job)
    t.update_fields(job.key, ats="reed", apply_url=job.url)
    t.set_status(job.key, Status.NEEDS_MANUAL, "reed has no reliable auto-apply")
    def no_tool_browser(*a, **k):
        raise AssertionError("tool browser must not start for Reed jobs")
    pipe.browser = no_tool_browser
    res = pipe.assist(prompt=lambda _: "a", open_normal=lambda u: None)
    assert res["applied"] == 1
    row = t.get(job.key)
    assert row["status"] == "applied" and row["apply_method"] == "user_confirmed"



def test_prepare_puts_auto_jobs_first_and_uncapped(settings, profile):
    t = Tracker(settings.db_path)
    pipe = Pipeline(settings, t, profile, sources_cfg={})
    for i in range(3):   # high-scoring manual jobs
        j = Job(source="reed", source_id=f"m{i}", title="Data Analyst", company=f"M{i}", description=DESC, url=f"https://r/{i}")
        t.add_found(j); t.update_fields(j.key, ats="reed", score=0.9); t.set_status(j.key, Status.SHORTLISTED, "")
    j = Job(source="lever", source_id="a/1", title="Data Analyst", company="Auto", description=DESC, url="https://jobs.lever.co/a/1")
    t.add_found(j); t.update_fields(j.key, ats="lever", score=0.2); t.set_status(j.key, Status.SHORTLISTED, "")
    pipe.prepare(limit=1, use_llm=False)
    assert t.get("lever:a/1")["status"] == "ready"                       # low score but auto -> prepared
    assert len(t.by_status(Status.NEEDS_MANUAL)) == 1                    # manual capped at limit
