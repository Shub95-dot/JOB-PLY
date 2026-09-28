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
