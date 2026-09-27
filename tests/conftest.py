import copy
from pathlib import Path

import pytest
import yaml

from src.content.profile import Profile
from src.core.config import ROOT, Settings

FORMS = Path(__file__).parent / "fixtures" / "forms"


@pytest.fixture
def profile():
    return Profile.load(ROOT / "config" / "user_profile.yaml")


@pytest.fixture
def answers_cfg():
    return yaml.safe_load(open(ROOT / "config" / "answers.yaml", encoding="utf-8"))


@pytest.fixture
def answered_cfg(answers_cfg):
    """answers.yaml with the TODO eligibility answers filled in (as a user would)."""
    cfg = copy.deepcopy(answers_cfg)
    fill = {"right_to_work": "Yes", "sponsorship": "No", "relocation": "Yes"}
    for r in cfg["rules"]:
        if r["id"] in fill:
            r["answer"] = fill[r["id"]]
    return cfg


@pytest.fixture
def cv(tmp_path):
    from reportlab.pdfgen import canvas
    p = tmp_path / "cv.pdf"
    c = canvas.Canvas(str(p))
    c.drawString(72, 720, "Shubham Shirodkar - Python SQL Power BI")
    c.save()
    return p


@pytest.fixture(scope="session")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def page(browser):
    ctx = browser.new_context()
    pg = ctx.new_page()
    yield pg
    ctx.close()


@pytest.fixture
def settings(tmp_path, cv):
    s = Settings({"profile_reviewed": True, "cv_path": str(cv),
                  "apply": {"daily_cap": 5, "min_score": 0.1, "headless": True,
                            "delay_between_applications_seconds": [0, 0], "confirmation_timeout_seconds": 6},
                  "paths": {}})
    s.db_path = tmp_path / "t.db"
    s.evidence_dir = tmp_path / "ev"
    s.digest_dir = tmp_path / "digest"
    s.browser_profile = tmp_path / "bp"
    return s
