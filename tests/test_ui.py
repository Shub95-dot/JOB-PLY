"""Interface smoke tests with Streamlit's AppTest on a sample tracker."""
import os
from pathlib import Path

import pytest

st_testing = pytest.importorskip("streamlit.testing.v1")

from src.core.models import Job, Status
from src.core.tracker import Tracker

APP = str(Path(__file__).resolve().parents[1] / "src" / "ui" / "app.py")


@pytest.fixture
def sample_db(tmp_path, monkeypatch):
    db = tmp_path / "t.db"
    monkeypatch.setenv("JOBPLY_DB", str(db))
    t = Tracker(db)
    j1 = Job(source="reed", source_id="1", title="Junior Data Analyst", company="Delta", location="Southampton",
             description="SQL and Python", url="https://www.reed.co.uk/jobs/x/1", work_type="Hybrid")
    j2 = Job(source="lever", source_id="zopa/1", title="Graduate Analyst", company="Zopa", location="London",
             description="SQL", url="https://jobs.lever.co/zopa/1", apply_url="https://jobs.lever.co/zopa/1/apply")
    j3 = Job(source="ashby", source_id="relay/1", title="Data Analyst", company="Relay", url="https://jobs.ashbyhq.com/relay/1")
    for j in (j1, j2, j3):
        t.add_found(j)
    t.update_fields(j1.key, ats="reed", score=0.6, cover_letter="Dear Hiring Team at Delta, ...")
    t.set_status(j1.key, Status.NEEDS_MANUAL, "reed has no reliable auto-apply — submit in assist mode")
    t.update_fields(j2.key, ats="lever", score=0.8, unanswered=["Did you complete A-level Maths? ✱ [radio] — no rule in answers.yaml"])
    t.set_status(j2.key, Status.NEEDS_MANUAL, "required questions without a configured answer")
    t.update_fields(j3.key, ats="ashby")
    t.set_status(j3.key, Status.APPLIED, "confirmation detected", confirmation_text="Thanks for applying | url")
    t.close()
    return db


def run_app():
    at = st_testing.AppTest.from_file(APP, default_timeout=30)
    at.run()
    assert not at.exception, at.exception
    return at


def test_app_renders_all_tabs(sample_db):
    at = run_app()
    labels = [m.label for m in at.metric]
    assert "Applied today" in labels and "Need you" in labels
    need_you = next(m for m in at.metric if m.label == "Need you")
    assert need_you.value == "2"
    assert len(at.tabs) == 6
    companies = set()
    for d in at.dataframe:
        if "company" in d.value.columns:
            companies |= set(d.value["company"])
    assert {"Zopa", "Delta", "Relay"} <= companies        # queue + applications tables
    # the unanswered-question summary lists the A-level question
    assert any("question" in d.value.columns and d.value["question"].str.contains("A-level").any()
               for d in at.dataframe)


def test_toggle_and_buttons_exist(sample_db):
    at = run_app()
    assert any(b.label.startswith("🧪 Dry run") for b in at.button)
    assert any(tg.label.startswith("Live") for tg in at.toggle)


def test_add_rule_and_config_validation(tmp_path, monkeypatch):
    import importlib.util, shutil
    cfg = tmp_path / "config"
    shutil.copytree(Path(__file__).resolve().parents[1] / "config", cfg)
    spec = importlib.util.spec_from_file_location("uiapp_helpers", APP)
    src = Path(APP).read_text(encoding="utf-8")
    helpers = src.split("# ============================================================================ sidebar")[0]
    ns = {"__file__": APP, "__name__": "helpers"}
    exec(compile(helpers.replace("st.set_page_config", "(lambda **k: None)"), APP, "exec"), ns)
    ns["CONFIG"] = cfg
    assert ns["validate_yaml"]("answers.yaml", "rules: [") is not None                 # broken YAML refused
    assert ns["validate_yaml"]("answers.yaml", "rules:\n  - id: x\n    patterns: ['(']") is not None  # bad regex
    assert ns["add_rule"]("a_level", "a-level math", "I completed an equivalent Maths course") is None
    text = (cfg / "answers.yaml").read_text(encoding="utf-8")
    assert text.index("id: a_level") < text.index("id: sponsorship")                     # inserted at the top
    assert "# Answers to application-form questions" in text                             # comments kept
    ns["set_scalar"](cfg / "settings.yaml", "daily_cap", 9)
    assert "daily_cap: 9" in (cfg / "settings.yaml").read_text() and "# max VERIFIED" in (cfg / "settings.yaml").read_text()


def test_apply_tab_has_links(sample_db):
    at = run_app()
    labels = [b.label for b in at.button]
    assert any(l.startswith("⏭ Skip") for l in labels)
    link_cols = [d for d in at.dataframe if "link" in d.value.columns]
    assert link_cols and link_cols[0].value["link"].str.startswith("https://").all()
