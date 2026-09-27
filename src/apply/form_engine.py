"""Generic, label-driven application-form filler (Playwright, sync API).

1. `scan()`   — read every visible form control and work out its question label,
                type, options and whether it is required.
2. `plan()`   — map each control to an answer from your profile / answers.yaml.
                Required controls with no configured answer are returned as `unanswered`;
                the caller then refuses to submit.
3. `fill()`   — type/select/upload the planned answers.
4. `still_empty_required()` — re-read the form after filling as a final check.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from src.apply.answers import Answers, Resolution, pick_option

log = logging.getLogger("form")

SCAN_JS = r"""
() => {
  const vis = el => { if (el.type === 'file') return true;
    const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return (r.width > 0 || r.height > 0) && s.visibility !== 'hidden' && s.display !== 'none'; };
  const txt = el => (el ? (el.innerText || el.textContent || '') : '').replace(/\s+/g, ' ').trim();
  const labelFor = el => {
    if (el.id) { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (l && txt(l)) return txt(l); }
    const lb = el.getAttribute('aria-labelledby');
    if (lb) { const t = lb.split(/\s+/).map(i => txt(document.getElementById(i))).join(' ').trim(); if (t) return t; }
    if (el.getAttribute('aria-label')) return el.getAttribute('aria-label');
    const wrap = el.closest('label'); if (wrap && txt(wrap)) return txt(wrap);
    return '';
  };
  // question text for a radio/checkbox group or an unlabeled control: climb until the container has
  // text that isn't just the options' own labels
  const questionText = (els, optionTexts) => {
    const fs = els[0].closest('fieldset'); if (fs) { const lg = fs.querySelector('legend'); if (lg && txt(lg)) return txt(lg); }
    const grp = els[0].closest('[role=radiogroup],[role=group]');
    if (grp) { const t = labelFor(grp); if (t) return t; }
    let node = els[0].parentElement;
    for (let i = 0; i < 6 && node; i++, node = node.parentElement) {
      if (!els.every(e => node.contains(e))) continue;
      let t = txt(node); for (const o of optionTexts) if (o) t = t.split(o).join(' ');
      t = t.replace(/\s+/g, ' ').trim();
      if (t.length > 1) return t.slice(0, 300);
    }
    return '';
  };
  const isReq = (el, label) => !!(el.required || el.getAttribute('aria-required') === 'true' || /[*✱]\s*$|[*✱]\s|\(required\)/i.test(label || '')
      || (el.closest('[class*=required i]') && !el.closest('form')?.isSameNode(el.closest('[class*=required i]'))));
  const out = []; let n = 0; const seenGroups = new Set();
  const controls = document.querySelectorAll('input, select, textarea');
  for (const el of controls) {
    const type = (el.tagName === 'INPUT' ? (el.getAttribute('type') || 'text') : el.tagName).toLowerCase();
    if (['hidden','submit','button','reset','image','search'].includes(type)) continue;
    if (el.disabled || !vis(el)) continue;
    if (el.closest('[aria-hidden=true]') && type !== 'file') continue;
    if ((type === 'radio' || type === 'checkbox') && el.name) {
      if (seenGroups.has(el.name)) continue; seenGroups.add(el.name);
      const els = [...document.querySelectorAll(`input[name="${CSS.escape(el.name)}"]`)].filter(vis);
      const opts = els.map(e => labelFor(e) || e.value);
      let q = questionText(els, opts);
      if (!q && els.length === 1) q = opts[0];
      const id = 'g' + (n++); els.forEach((e, i) => e.setAttribute('data-jaa', id + '_' + i));
      out.push({id, kind: type, label: q, options: opts, required: els.some(e => isReq(e, q)) || /[*✱]/.test(q), name: el.name,
                value: els.filter(e => e.checked).map((e, i) => opts[els.indexOf(e)]).join('|')});
      continue;
    }
    const id = 'f' + (n++); el.setAttribute('data-jaa', id);
    let label = labelFor(el);
    if (!label) label = questionText([el], []) || el.getAttribute('placeholder') || el.name || '';
    let kind = el.tagName === 'SELECT' ? 'select' : el.tagName === 'TEXTAREA' ? 'textarea' : type;
    if (el.getAttribute('role') === 'combobox' && el.tagName === 'INPUT') kind = 'combobox';
    const options = el.tagName === 'SELECT' ? [...el.options].map(o => o.text.trim()) : [];
    out.push({id, kind, label, options, required: isReq(el, label), name: el.name || el.id || '',
              value: kind === 'file' ? (el.files && el.files.length ? 'file' : '') : (el.value || '')});
  }
  return out;
}
"""


@dataclass
class Control:
    id: str
    kind: str
    label: str
    options: list[str]
    required: bool
    name: str
    value: str = ""


@dataclass
class Action:
    control: Control
    value: str          # text / chosen option / file path
    rule: str


@dataclass
class Plan:
    actions: list[Action] = field(default_factory=list)
    unanswered: list[str] = field(default_factory=list)   # required questions you need to answer
    skipped_optional: list[str] = field(default_factory=list)


class FormEngine:
    def __init__(self, page, answers: Answers, cv_path: Path, cover_letter_path: Optional[Path]):
        self.page = page
        self.answers = answers
        self.cv_path = cv_path
        self.cl_path = cover_letter_path

    def scan(self) -> list[Control]:
        return [Control(**c) for c in self.page.evaluate(SCAN_JS)]

    def plan(self, controls: Optional[list[Control]] = None) -> Plan:
        plan = Plan()
        for c in controls if controls is not None else self.scan():
            res = self.answers.resolve(c.label, c.kind)
            value = self._value_for(c, res)
            if value is None:
                if c.required:
                    why = "answer is TODO in answers.yaml" if res.todo else (
                        f"no option matched '{res.value}'" if res.value else "no rule in answers.yaml")
                    plan.unanswered.append(f"{c.label or c.name} [{c.kind}] — {why}")
                else:
                    plan.skipped_optional.append(c.label or c.name)
                continue
            plan.actions.append(Action(c, value, res.rule))
        return plan

    def _value_for(self, c: Control, res: Resolution) -> Optional[str]:
        if c.kind == "file":
            if res.rule == "resume":
                return str(self.cv_path)
            if res.rule == "cover_letter_file" and self.cl_path:
                return str(self.cl_path)
            return None
        if c.kind in ("select", "radio"):
            return pick_option(c.options, res)
        if c.kind == "checkbox":
            if len(c.options) == 1:          # single consent/acknowledgement box
                if res.value and res.value.lower() in ("yes", "true", "agree", "checked", "1"):
                    return c.options[0]
                return None
            return pick_option(c.options, res)   # multi-select: tick the matching option
        return res.value if (res.value or "").strip() else None

    # ------------------------------------------------------------------ fill
    def fill(self, plan: Plan) -> list[dict]:
        done = []
        for a in plan.actions:
            c = a.control
            try:
                if c.kind == "file":
                    self.page.locator(f'[data-jaa="{c.id}"]').set_input_files(a.value)
                elif c.kind == "select":
                    self.page.locator(f'[data-jaa="{c.id}"]').select_option(label=a.value)
                elif c.kind in ("radio", "checkbox"):
                    idx = c.options.index(a.value)
                    loc = self.page.locator(f'[data-jaa="{c.id}_{idx}"]')
                    try:
                        loc.check(timeout=3000)
                    except Exception:
                        loc.check(force=True, timeout=3000)
                elif c.kind == "combobox":
                    loc = self.page.locator(f'[data-jaa="{c.id}"]')
                    loc.click()
                    loc.fill(a.value)
                    opt = self.page.locator("[role=option]").filter(has_text=a.value).first
                    try:
                        opt.click(timeout=2500)
                    except Exception:
                        loc.press("Enter")
                else:
                    self.page.locator(f'[data-jaa="{c.id}"]').fill(a.value)
                done.append({"label": c.label, "kind": c.kind, "rule": a.rule,
                             "value": a.value if c.kind != "textarea" else a.value[:120] + "…"})
            except Exception as e:
                log.warning("could not fill '%s': %s", c.label, e)
                if c.required:
                    plan.unanswered.append(f"{c.label} [{c.kind}] — fill failed: {e.__class__.__name__}")
        return done

    def still_empty_required(self) -> list[str]:
        return [f"{c.label or c.name} [{c.kind}] — still empty after filling"
                for c in self.scan() if c.required and not c.value]
