"""Daily HTML digest (saved to data/digest/) + optional email via any SMTP server."""
from __future__ import annotations

import html
import logging
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from src.core.config import env
from src.core.models import Status
from src.core.tracker import Tracker, row_list

log = logging.getLogger("digest")

CSS = """
:root{--bg:#fff;--fg:#1d1d1f;--muted:#6b6b70;--line:#e4e4e7;--ok:#137333;--warn:#a15c00;--bad:#b3261e;--card:#fafafa}
@media (prefers-color-scheme:dark){:root{--bg:#141416;--fg:#ececef;--muted:#9a9aa2;--line:#2c2c31;--ok:#6fcf8a;--warn:#f0b35a;--bad:#f28b82;--card:#1c1c20}}
body{font:14px/1.5 system-ui,-apple-system,Segoe UI,sans-serif;background:var(--bg);color:var(--fg);max-width:960px;margin:0 auto;padding:24px 16px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:28px 0 8px;border-bottom:1px solid var(--line);padding-bottom:6px}
.muted{color:var(--muted)}.stats{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0}
.stat{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 14px;min-width:110px}
.stat b{display:block;font-size:20px}table{width:100%;border-collapse:collapse}
td,th{text-align:left;padding:7px 6px;border-bottom:1px solid var(--line);vertical-align:top}th{font-weight:600;color:var(--muted);font-size:12px}
a{color:inherit}.ok{color:var(--ok)}.warn{color:var(--warn)}.bad{color:var(--bad)}ul{margin:4px 0 0 18px;padding:0}
.scroll{overflow-x:auto}
"""


def why_bucket(r) -> str:
    """Plain-English reason a job couldn't be auto-submitted."""
    reason = (r["reason"] or "").lower()
    if r["status"] == Status.FAILED.value:
        return "Submission attempted but not confirmed"
    if "captcha" in reason:
        return "CAPTCHA on the form"
    if row_list(r, "unanswered"):
        return "Form asks a question you haven't answered in answers.yaml"
    if "no reliable auto-apply" in reason or "site" in reason:
        return f"Site can't be auto-submitted ({r['ats'] or 'unknown'})"
    return reason[:60] or "Other"


def breakdown(rows) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        k = why_bucket(r)
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def build(tracker: Tracker, day: date | None = None) -> str:
    d = day or date.today()
    applied = tracker.applied_on(d)
    manual = tracker.by_status(Status.NEEDS_MANUAL)
    failed = tracker.by_status(Status.FAILED)
    ready = tracker.by_status(Status.READY)
    due = tracker.follow_ups_due(d)
    c = tracker.counts()
    e = html.escape

    def link(r):
        return f'<a href="{e(r["apply_url"] or r["url"] or "")}">{e(r["title"])}</a>'

    rows_applied = "".join(
        f"<tr><td>{link(r)}</td><td>{e(r['company'])}</td><td>{e(r['work_type'] or '')}</td><td>{e(r['apply_method'] or '')}</td>"
        f"<td class=muted>{e((r['confirmation_text'] or 'confirmed by you')[:140])}</td></tr>" for r in applied)
    rows_why = "".join(f"<tr><td>{e(k)}</td><td>{v}</td></tr>" for k, v in breakdown(manual + failed).items())
    rows_manual = "".join(
        f"<tr><td>{link(r)}</td><td>{e(r['company'])}</td><td>{e(r['work_type'] or '')}<br><span class=muted>{e(r['location'] or '')}</span></td>"
        f"<td>{e(r['source'])} → {e(r['ats'] or '?')}</td><td>{(r['score'] or 0):.2f}</td>"
        f"<td>{e(r['reason'] or '')}{'<ul>' + ''.join(f'<li>{e(q)}</li>' for q in row_list(r, 'unanswered')) + '</ul>' if row_list(r, 'unanswered') else ''}</td></tr>"
        for r in manual[:60])
    rows_failed = "".join(
        f"<tr><td>{link(r)}</td><td>{e(r['company'])}</td><td class=bad>{e(r['reason'] or '')}</td></tr>" for r in failed[:30])
    rows_due = "".join(
        f"<tr><td>{link(r)}</td><td>{e(r['company'])}</td><td>{e((r['applied_at'] or '')[:10])}</td></tr>" for r in due)

    def table(head, rows, empty):
        if not rows:
            return f"<p class=muted>{empty}</p>"
        return f"<div class=scroll><table><tr>{''.join(f'<th>{h}</th>' for h in head)}</tr>{rows}</table></div>"

    stat = lambda label, n, cls="": f'<div class=stat><b class="{cls}">{n}</b><span class=muted>{label}</span></div>'
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Job digest {d.isoformat()}</title><style>{CSS}</style></head><body>
<h1>Job applications — {d.strftime('%a %d %b %Y')}</h1>
<p class=muted>“Applied” only lists submissions confirmed by the employer's confirmation page or by you.</p>
<div class=stats>{stat('verified today', len(applied), 'ok')}{stat('need you', len(manual), 'warn')}{stat('failed', len(failed), 'bad')}
{stat('queued for auto', len(ready))}{stat('applied, all time', c.get('applied', 0))}{stat('follow-ups due', len(due))}</div>
<h2>Applied today (verified)</h2>{table(['Role','Company','Type','How','Confirmation'], rows_applied, 'None today.')}
<h2>Could not auto-apply — why</h2>{table(['Reason','Jobs'], rows_why, 'Nothing blocked.')}
<h2>Needs you — run <code>python main.py assist</code></h2>{table(['Role','Company','Type / location','Found on → apply via','Score','Why'], rows_manual, 'Nothing waiting.')}
<h2>Failed submissions (will retry in assist)</h2>{table(['Role','Company','Error'], rows_failed, 'None.')}
<h2>Follow-ups due</h2>{table(['Role','Company','Applied'], rows_due, 'None due.')}
</body></html>"""


def save(tracker: Tracker, out_dir: Path, day: date | None = None) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    d = day or date.today()
    p = out_dir / f"digest_{d.isoformat()}.html"
    p.write_text(build(tracker, d), encoding="utf-8")
    return p


def email(html_body: str, subject: str) -> bool:
    host, user, pwd, to = env("SMTP_HOST"), env("SMTP_USER"), env("SMTP_PASSWORD"), env("NOTIFY_TO")
    if not (host and user and pwd and to):
        log.info("SMTP not configured — digest saved to file only")
        return False
    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["From"], msg["To"] = subject, user, to
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    try:
        with smtplib.SMTP(host, int(env("SMTP_PORT", "587")), timeout=30) as s:
            s.starttls()
            s.login(user, pwd)
            s.sendmail(user, [to], msg.as_string())
        return True
    except Exception as e:
        log.error("email failed: %s", e)
        return False
