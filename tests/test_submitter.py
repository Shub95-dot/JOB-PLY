"""End-to-end submission tests against local copies of ATS form layouts."""
import json

from src.apply.answers import Answers
from src.apply.submitter import Submitter
from src.core.models import Status
from tests.conftest import FORMS


def _sub(page, ats, cfg, profile, cv, tmp_path, letter="Dear Hiring Team at Gamma, ..."):
    return Submitter(page, ats, Answers(cfg, profile, letter), cv, None, tmp_path / "ev", confirm_timeout_s=6)


def test_lever_submits_and_verifies(page, answered_cfg, profile, cv, tmp_path):
    out = _sub(page, "lever", answered_cfg, profile, cv, tmp_path).apply((FORMS / "lever_form.html").as_uri())
    assert out.status == Status.APPLIED, out
    assert "Application submitted" in out.confirmation_text
    sent = json.loads(page.evaluate("localStorage.getItem('last')") or "{}")
    assert sent["name"] == "Shubham S. Shirodkar"
    assert sent["email"] == "shirodkarshubham9@gmail.com"
    assert sent["resume"] == "cv.pdf"
    assert sent["cards[abc][field0]"] == "Yes"
    assert sent["eeo[gender]"] == "Decline to self-identify"
    assert sent["org"] == "KFC"
    assert (tmp_path / "ev" / "confirmation.png").exists()
    assert (tmp_path / "ev" / "form_filled.png").exists()


def test_lever_refuses_when_right_to_work_is_todo(page, answers_cfg, profile, cv, tmp_path):
    out = _sub(page, "lever", answers_cfg, profile, cv, tmp_path).apply((FORMS / "lever_form.html").as_uri())
    assert out.status == Status.NEEDS_MANUAL
    assert any("right to work" in q.lower() for q in out.unanswered)
    assert page.evaluate("localStorage.getItem('last')") is None  # nothing was sent


def test_greenhouse_text_confirmation(page, answered_cfg, profile, cv, tmp_path):
    out = _sub(page, "greenhouse", answered_cfg, profile, cv, tmp_path).apply((FORMS / "greenhouse_form.html").as_uri())
    assert out.status == Status.APPLIED, out
    assert "Thank you for applying" in out.confirmation_text


def test_greenhouse_dry_run_does_not_submit(page, answered_cfg, profile, cv, tmp_path):
    out = _sub(page, "greenhouse", answered_cfg, profile, cv, tmp_path).apply(
        (FORMS / "greenhouse_form.html").as_uri(), dry_run=True)
    assert out.status == Status.READY
    assert "Thank you" not in page.inner_text("body")
    assert page.input_value("#first_name") == "Shubham"
    assert page.input_value("#last_name") == "Shirodkar"


def test_ashby_radio_and_motivation(page, answered_cfg, profile, cv, tmp_path):
    out = _sub(page, "ashby", answered_cfg, profile, cv, tmp_path).apply((FORMS / "ashby_form.html").as_uri())
    assert out.status == Status.APPLIED, out


def test_captcha_goes_to_manual(page, answered_cfg, profile, cv, tmp_path):
    out = _sub(page, "lever", answered_cfg, profile, cv, tmp_path).apply((FORMS / "captcha_form.html").as_uri())
    assert out.status == Status.NEEDS_MANUAL
    assert "CAPTCHA" in out.detail


def test_rejected_submission_is_failed_not_applied(page, answered_cfg, profile, cv, tmp_path):
    out = _sub(page, "lever", answered_cfg, profile, cv, tmp_path).apply((FORMS / "broken_form.html").as_uri())
    assert out.status == Status.FAILED


def test_yes_no_never_typed_into_text_and_followups_skipped(page, answered_cfg, profile, cv, tmp_path):
    import copy
    cfg = copy.deepcopy(answered_cfg)
    cfg["rules"].insert(0, {"id": "graduate_visa", "patterns": ["graduate visa"], "answer": "Yes"})
    html = """<form id=application-form>
      <label>Full name ✱<input name=name required></label>
      <label>Email ✱<input name=email type=email required></label>
      <label>Resume ✱<input type=file name=resume required></label>
      <div class=q><div>Will you be on a Graduate visa by your start date? ✱</div>
        <label><input type=radio name=gv value=Yes required>Yes</label><label><input type=radio name=gv value=No>No</label></div>
      <label>If you selected yes, please provide details of your Graduate visa status<textarea name=gvd></textarea></label>
      <label>Graduate visa reference<input name=gvref></label>
      <button id=btn-submit type=submit>Submit application</button></form>"""
    p = tmp_path / "f.html"
    p.write_text(html, encoding="utf-8")
    from src.apply.answers import Answers
    from src.apply.form_engine import FormEngine
    page.goto(p.as_uri())
    eng = FormEngine(page, Answers(cfg, profile), cv, None)
    plan = eng.plan()
    filled = {a.control.label.split("\n")[0][:40]: a.value for a in plan.actions}
    assert any(v == "Yes" for k, v in filled.items() if "Graduate visa by" in k)       # radio answered
    assert not any("details" in k for k in filled)                                       # follow-up left alone
    assert not any("reference" in k for k in filled)                                     # no "Yes" typed into text
