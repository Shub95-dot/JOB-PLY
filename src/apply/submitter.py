"""Submits applications on Greenhouse / Lever / Ashby hosted forms and VERIFIES them.

An application only counts as APPLIED when, after clicking submit, the ATS shows its
confirmation page/message. The confirmation text, final URL and before/after screenshots
are saved under data/evidence/<job>/.

Never submits when:
  * any required question has no configured answer (-> NEEDS_MANUAL, questions listed);
  * a visible CAPTCHA challenge is present (-> NEEDS_MANUAL; finish it in assist mode);
  * the form still shows empty required fields after filling.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.apply.answers import Answers
from src.apply.form_engine import FormEngine
from src.core.models import ApplyOutcome, Status

log = logging.getLogger("submitter")


@dataclass
class Adapter:
    name: str
    open_form: Optional[str]         # selector of an "Apply" button to reveal the form, if any
    submit: list[str]                # submit-button selectors, tried in order
    success_url: re.Pattern
    success_text: re.Pattern
    ready: str                       # selector that means the form has rendered


ADAPTERS = {
    "greenhouse": Adapter(
        "greenhouse", open_form="button:has-text('Apply'):not([type=submit])",
        submit=["button[type=submit]:has-text('Submit')", "#submit_app", "input[type=submit]", "button[type=submit]"],
        success_url=re.compile(r"/confirmation|/thanks|application_confirmation", re.I),
        success_text=re.compile(r"thank you for applying|application (has been |was )?(submitted|received)|"
                                r"we('ve| have) received your application", re.I),
        ready="form, #application_form, #application-form"),
    "lever": Adapter(
        "lever", open_form=None,
        submit=["#btn-submit", "button[type=submit]:has-text('Submit')", "button[type=submit]"],
        success_url=re.compile(r"/thanks\b", re.I),
        success_text=re.compile(r"application submitted|thanks? (you )?for applying|we('ve| have) received your application", re.I),
        ready="form#application-form, form"),
    "ashby": Adapter(
        "ashby", open_form=None,
        submit=["button:has-text('Submit Application')", "button[type=submit]", "button:has-text('Submit')"],
        success_url=re.compile(r"/submitted|/thank", re.I),
        success_text=re.compile(r"thanks? (you )?for applying|application (was |has been )?(submitted|received)|"
                                r"successfully submitted", re.I),
        ready="form, [class*=application-form]"),
}

CAPTCHA_SEL = ("iframe[src*='hcaptcha.com'][src*='challenge'], iframe[title*='challenge' i], "
               "iframe[src*='recaptcha'][src*='bframe'], iframe[src*='recaptcha/api2/anchor'], "
               ".h-captcha:not([data-size=invisible]), .g-recaptcha:not([data-size=invisible]), "
               "iframe[src*='challenges.cloudflare.com']")
ERROR_TEXT = re.compile(r"(this field is required|is required|please (complete|fill|enter|select)|"
                        r"there (was|were) (an )?errors?|invalid (email|phone|value)|something went wrong)", re.I)


def visible_captcha(page) -> bool:
    for el in page.locator(CAPTCHA_SEL).all():
        try:
            if el.is_visible():
                box = el.bounding_box()
                if box and box["width"] > 30 and box["height"] > 30:
                    return True
        except Exception:
            continue
    return False


class Submitter:
    def __init__(self, page, ats: str, answers: Answers, cv_path: Path, cover_letter_path: Optional[Path],
                 evidence_dir: Path, confirm_timeout_s: int = 25):
        self.page = page
        self.ad = ADAPTERS[ats]
        self.answers = answers
        self.cv_path = cv_path
        self.cl_path = cover_letter_path
        self.evidence = evidence_dir
        self.timeout = confirm_timeout_s
        self._pre_success = False
        evidence_dir.mkdir(parents=True, exist_ok=True)

    def apply(self, form_url: str, dry_run: bool = False) -> ApplyOutcome:
        p = self.page
        try:
            p.goto(form_url, wait_until="domcontentloaded", timeout=45000)
            p.wait_for_load_state("networkidle", timeout=15000)
        except Exception as e:
            if "Timeout" not in str(e) or p.url in ("about:blank", ""):
                return ApplyOutcome(status=Status.FAILED, detail=f"could not open form: {e}")
        if re.search(r"no longer (accepting|available)|position (has been )?(filled|closed)|job not found|page not found",
                     _body(p), re.I):
            return ApplyOutcome(status=Status.SKIPPED, detail="posting closed")
        if self.ad.open_form:
            btn = p.locator(self.ad.open_form).first
            try:
                if btn.is_visible(timeout=1500):
                    btn.click()
                    p.wait_for_timeout(1200)
            except Exception:
                pass
        try:
            p.wait_for_selector(self.ad.ready, timeout=15000)
        except Exception:
            return ApplyOutcome(status=Status.NEEDS_MANUAL, detail="application form not found on page",
                                evidence_dir=str(self.evidence))

        engine = FormEngine(p, self.answers, self.cv_path, self.cl_path)
        plan = engine.plan()
        if plan.unanswered:
            self._shot("form_unanswered.png")
            return ApplyOutcome(status=Status.NEEDS_MANUAL, detail="required questions without a configured answer",
                                unanswered=plan.unanswered, evidence_dir=str(self.evidence))
        filled = engine.fill(plan)
        p.wait_for_timeout(800)
        leftover = plan.unanswered + engine.still_empty_required()
        (self.evidence / "filled_answers.json").write_text(json.dumps(filled, indent=2), encoding="utf-8")
        self._shot("form_filled.png")
        if leftover:
            return ApplyOutcome(status=Status.NEEDS_MANUAL, detail="required fields still empty after filling",
                                unanswered=leftover, evidence_dir=str(self.evidence))
        if visible_captcha(p):
            return ApplyOutcome(status=Status.NEEDS_MANUAL, detail="CAPTCHA on form — finish in assist mode",
                                evidence_dir=str(self.evidence))
        if dry_run:
            return ApplyOutcome(status=Status.READY, detail=f"dry run: form filled ({len(filled)} fields), not submitted",
                                evidence_dir=str(self.evidence))

        before_url = p.url
        self._pre_success = bool(self.ad.success_text.search(_body(p)))
        if not self._click_submit():
            return ApplyOutcome(status=Status.NEEDS_MANUAL, detail="submit button not found",
                                evidence_dir=str(self.evidence))
        return self._verify(before_url)

    # ------------------------------------------------------------------ helpers
    def _click_submit(self) -> bool:
        for sel in self.ad.submit:
            loc = self.page.locator(sel)
            for i in range(loc.count() - 1, -1, -1):   # last matching button is usually the real submit
                b = loc.nth(i)
                try:
                    if b.is_visible() and b.is_enabled():
                        b.scroll_into_view_if_needed()
                        b.click()
                        return True
                except Exception:
                    continue
        return False

    def _verify(self, before_url: str) -> ApplyOutcome:
        p = self.page
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            p.wait_for_timeout(1000)
            url, body = p.url, _body(p)
            m = self.ad.success_text.search(body)
            if m and self._pre_success and url == before_url:
                m = None   # that text was already on the form page — not proof of submission
            if (self.ad.success_url.search(url) and url != before_url) or m:
                snippet = _around(body, m) if m else body[:300]
                self._shot("confirmation.png")
                (self.evidence / "confirmation.txt").write_text(f"URL: {url}\n\n{body[:4000]}", encoding="utf-8")
                return ApplyOutcome(status=Status.APPLIED, detail="confirmation page detected",
                                    confirmation_text=f"{snippet} | {url}", evidence_dir=str(self.evidence))
            if visible_captcha(p):
                self._shot("captcha.png")
                return ApplyOutcome(status=Status.NEEDS_MANUAL,
                                    detail="CAPTCHA challenge appeared after submit — finish in assist mode",
                                    evidence_dir=str(self.evidence))
            invalid = p.locator("[aria-invalid=true]:visible").count()
            err = ERROR_TEXT.search(body)
            if (invalid or err) and url == before_url and time.time() > deadline - self.timeout + 3:
                self._shot("submit_error.png")
                return ApplyOutcome(status=Status.FAILED,
                                    detail=f"form rejected submission: {err.group(0) if err else f'{invalid} invalid fields'}",
                                    evidence_dir=str(self.evidence))
        self._shot("no_confirmation.png")
        return ApplyOutcome(status=Status.FAILED, detail=f"no confirmation within {self.timeout}s (url {p.url})",
                            evidence_dir=str(self.evidence))

    def _shot(self, name: str) -> None:
        try:
            self.page.screenshot(path=str(self.evidence / name), full_page=True)
        except Exception as e:
            log.debug("screenshot failed: %s", e)


def _body(page) -> str:
    try:
        return page.inner_text("body", timeout=3000)
    except Exception:
        return ""


def _around(text: str, m: re.Match, width: int = 120) -> str:
    s, e = max(0, m.start() - width // 2), min(len(text), m.end() + width)
    return re.sub(r"\s+", " ", text[s:e]).strip()
