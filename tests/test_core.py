import json

import pytest

from src.apply import ats
from src.apply.answers import Answers, pick_option
from src.content.cover_letter import CoverLetterWriter
from src.core.models import Job, Status
from src.core.tracker import EvidenceRequired, Tracker
from src.jobs.filter import JobFilter
from src.legacy import import_legacy


def J(**kw):
    base = dict(source="greenhouse", source_id="acme/1", title="Graduate Data Analyst", company="Acme",
                location="London, UK", url="https://x", description="We use SQL, Python and Power BI. " * 5)
    base.update(kw)
    return Job(**base)


# ---------------------------------------------------------------- filter
@pytest.fixture
def jf():
    return JobFilter()


@pytest.mark.parametrize("title,ok", [
    ("Graduate Data Analyst", True), ("Junior Data Analyst (Hybrid)", True), ("Reporting Analyst", True),
    ("Senior Data Analyst", False), ("Data Scientist II - ML Infrastructure", False),
    ("Remote Data Entry Clerk", False), ("Video Data Annotator", False), ("Lead BI Analyst", False),
    ("Trainee Data Analyst", False), ("Warehouse Operative", False), ("Data Analyst Manager", False),
])
def test_titles(jf, title, ok):
    assert jf.evaluate(J(title=title)).accepted is ok


def test_years(jf):
    assert jf.required_years("You will have 3+ years of experience in SQL") == 3
    assert jf.required_years("minimum of 5 years' commercial experience") == 5
    assert jf.required_years("1-2 years experience preferred") == 1
    assert jf.required_years("a 12 month contract") is None
    assert not jf.evaluate(J(description="Requires 4+ years experience with SQL and Python. " * 3)).accepted


def test_non_english_and_location(jf):
    de = "Wir suchen einen Kundenservice Mitarbeiter mit Erfahrung in Datenanalyse und Deutschkenntnissen für unser Team in Berlin sofort"
    assert not jf.evaluate(J(title="Data Analyst", description=de * 2)).accepted
    assert not jf.evaluate(J(location="Duarte, California")).accepted
    assert jf.evaluate(J(source="reed", source_id="1", location="Anywhere")).accepted  # Reed is UK-only
    assert not jf.evaluate(J(company="ITOL Recruit")).accepted


# ---------------------------------------------------------------- tracker
def test_applied_requires_evidence(tmp_path):
    t = Tracker(tmp_path / "t.db")
    j = J()
    assert t.add_found(j)
    assert not t.add_found(j)                                   # same id
    assert not t.add_found(J(source="reed", source_id="9", title="Graduate Data Analyst (Hybrid)", company="Acme Ltd"))  # cross-post
    with pytest.raises(EvidenceRequired):
        t.set_status(j.key, Status.APPLIED, "claimed")
    t.set_status(j.key, Status.APPLIED, "ok", confirmation_text="Application submitted | url")
    assert t.get(j.key)["follow_up_date"]
    assert t.count_applied_today() == 1
    assert [e["to_status"] for e in t.events_for(j.key)] == ["found", "applied"]


def test_legacy_import(tmp_path):
    old = {
        "a": {"job_title": "Data Analyst", "company": "KP Law", "status": "submitted", "submitted_at": "2026-09-23",
              "url": "https://uk.linkedin.com/jobs/view/data-analyst-at-kp-law-4469714541?position=1"},
        "b": {"job_title": "Junior Data Analyst", "company": "TechMetrics Ltd", "url": "https://example.com/jobs/jr-data-analyst-1"},
        "c": {"job_title": "Trainee", "company": "ITOL", "url": "https://www.reed.co.uk/jobs/data-analyst-jobs?keywords=data+analyst"},
        "d": {"job_title": "Data Analyst", "company": "KP Law", "url": "https://uk.linkedin.com/jobs/view/data-analyst-at-kp-law-4469714541?position=9"},
    }
    f = tmp_path / "old.json"
    f.write_text(json.dumps(old))
    t = Tracker(tmp_path / "t.db")
    st = import_legacy(f, t)
    assert st == {"imported": 1, "fake_dropped": 2, "duplicates": 1}
    assert t.counts() == {"legacy_unverified": 1}


# ---------------------------------------------------------------- ATS detection
@pytest.mark.parametrize("url,name,form", [
    ("https://job-boards.greenhouse.io/monzo/jobs/123456", "greenhouse", "https://job-boards.greenhouse.io/monzo/jobs/123456"),
    ("https://boards.greenhouse.io/embed/job_app?for=acme&token=987", "greenhouse", "https://job-boards.greenhouse.io/acme/jobs/987"),
    ("https://jobs.lever.co/acme/0f7a3b1c-1111-2222-3333-444455556666", "lever", "https://jobs.lever.co/acme/0f7a3b1c-1111-2222-3333-444455556666/apply"),
    ("https://jobs.eu.lever.co/acme/0f7a3b1c-1111-2222-3333-444455556666/apply", "lever", "https://jobs.eu.lever.co/acme/0f7a3b1c-1111-2222-3333-444455556666/apply"),
    ("https://jobs.ashbyhq.com/gamma/0f7a3b1c-1111-2222-3333-444455556666", "ashby", "https://jobs.ashbyhq.com/gamma/0f7a3b1c-1111-2222-3333-444455556666/application"),
    ("https://www.reed.co.uk/jobs/data-analyst/5735521", "reed", None),
    ("https://uk.linkedin.com/jobs/view/123", "linkedin", None),
])
def test_detect(url, name, form):
    t = ats.detect(url)
    assert t.ats == name and t.form_url == form


# ---------------------------------------------------------------- answers
def test_answers(answers_cfg, profile):
    a = Answers(answers_cfg, profile)
    assert a.resolve("First name*", "text").value == "Shubham"
    assert a.resolve("Do you have the right to work in the UK?", "radio").todo
    assert a.resolve("Will you require visa sponsorship?", "select").todo
    assert a.resolve("Gender", "select").decline
    assert a.resolve("Would you like to receive emails about our products?", "radio").rule == "unknown"
    assert pick_option(["Select...", "Male", "Female", "I don't wish to answer"], a.resolve("Gender", "select")) == "I don't wish to answer"


# ---------------------------------------------------------------- cover letter guard
def test_cover_letter_template_passes_guard(profile):
    w = CoverLetterWriter(profile, use_llm=False)
    job = J(description="We need SQL, Python and Power BI for dashboards and reporting. " * 4)
    letter = w.write(job, ["python", "sql", "power bi"])
    assert letter.method == "template"
    assert w.check(letter.text, job) == [], letter.text
    assert "Data Solutions Lab" not in letter.text
    assert "0.889" in letter.text               # verified, published figure may be used


def test_unverified_metrics_are_never_used(profile):
    for pr in profile.projects:
        pr["verified"] = False
        pr["results"] = ["Cut costs by 77%"]
    w = CoverLetterWriter(profile, use_llm=False)
    job = J(description="We need SQL, Python and Power BI for dashboards and reporting. " * 4)
    letter = w.write(job, ["python", "sql"])
    assert "77" not in letter.text and w.check(letter.text, job) == []


def test_cover_letter_guard_catches_invented_numbers(profile):
    w = CoverLetterWriter(profile, use_llm=False)
    job = J()
    fake = ("Dear Hiring Team at Acme, " + "I cut reporting time by 43% at my last analyst job. " + "word " * 160)
    assert any("numbers not in your profile" in p for p in w.check(fake, job))
