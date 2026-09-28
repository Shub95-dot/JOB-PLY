"""JOB-PLY web interface — run with:  python main.py ui   (opens http://localhost:8501)

Everything here reads/writes the same tracker, config files and evidence folders as the
command line, so you can mix both. Long jobs (runs) are started as background processes
that respect the same run lock as the scheduled task.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402
import yaml  # noqa: E402

from src.core.config import Settings, load_env, env  # noqa: E402
from src.core.lock import lock_info  # noqa: E402
from src.core.models import Status  # noqa: E402
from src.core.tracker import Tracker, row_list  # noqa: E402
from src.notify.digest import breakdown, why_bucket  # noqa: E402

st.set_page_config(page_title="JOB-PLY", page_icon="💼", layout="wide")
load_env()

PY = sys.executable
CONFIG = ROOT / "config"
LOG_UI = ROOT / "logs" / "ui_run.log"
ATS_AUTO = {"greenhouse", "lever", "ashby"}
NO_WINDOW = 0x08000000 if os.name == "nt" else 0          # CREATE_NO_WINDOW on Windows


# ============================================================================ helpers
def settings() -> Settings:
    return Settings()


def tracker() -> Tracker:
    return Tracker(settings().db_path)


def spawn(args: list[str], log_to: Path | None = LOG_UI) -> None:
    """Start `python main.py <args>` in the background."""
    kw = {"cwd": str(ROOT), "creationflags": NO_WINDOW} if os.name == "nt" else {"cwd": str(ROOT)}
    if log_to:
        log_to.parent.mkdir(exist_ok=True)
        f = open(log_to, "w", encoding="utf-8")
        f.write(f"$ python main.py {' '.join(args)}\n")
        f.flush()
        subprocess.Popen([PY, "-u", str(ROOT / "main.py"), *args], stdout=f, stderr=subprocess.STDOUT, **kw)
    else:
        subprocess.Popen([PY, str(ROOT / "main.py"), *args], **kw)


def running() -> dict | None:
    return lock_info(settings().db_path.parent / "run.lock")


def tail(path: Path, n: int = 60) -> str:
    try:
        return "".join(path.read_text(encoding="utf-8", errors="replace").splitlines(True)[-n:])
    except OSError:
        return ""


def set_scalar(path: Path, key: str, value) -> None:
    """Change `key: value` in a YAML file without losing its comments."""
    text = path.read_text(encoding="utf-8")
    v = "true" if value is True else "false" if value is False else str(value)
    new, n = re.subn(rf"(?m)^(\s*{re.escape(key)}:\s*)([^#\n]*?)(\s*(#.*)?)$", rf"\g<1>{v}\g<3>", text, count=1)
    if n != 1:
        raise ValueError(f"{key} not found in {path.name}")
    path.write_text(new, encoding="utf-8")


def validate_yaml(name: str, text: str) -> str | None:
    """Return an error message, or None if the file is usable."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        return f"YAML error: {e}"
    if name == "answers.yaml":
        rules = (data or {}).get("rules")
        if not isinstance(rules, list):
            return "answers.yaml must have a `rules:` list"
        for i, r in enumerate(rules):
            if not isinstance(r, dict) or "id" not in r or not isinstance(r.get("patterns"), list):
                return f"rule #{i + 1} needs `id` and a `patterns` list"
            for p in r["patterns"]:
                try:
                    re.compile(p)
                except re.error as e:
                    return f"rule '{r['id']}': bad pattern {p!r}: {e}"
    if name == "user_profile.yaml" and not (data or {}).get("name"):
        return "user_profile.yaml needs a `name`"
    return None


def save_config(name: str, text: str) -> str | None:
    err = validate_yaml(name, text)
    if err:
        return err
    path = CONFIG / name
    (CONFIG / f"{name}.bak").write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    path.write_text(text, encoding="utf-8")
    return None


def add_rule(rule_id: str, pattern: str, answer: str) -> str | None:
    """Insert a rule at the top of answers.yaml (first match wins), keeping comments."""
    path = CONFIG / "answers.yaml"
    text = path.read_text(encoding="utf-8")
    block = (f"  - id: {rule_id}\n"
             f"    patterns: [{json.dumps(pattern)}]\n"
             f"    answer: {json.dumps(answer) if answer.strip().upper() != 'TODO' else 'TODO'}\n")
    new = re.sub(r"(?m)^rules:\s*\n", lambda m: m.group(0) + block, text, count=1)
    return save_config("answers.yaml", new)


def unanswered_summary(t: Tracker) -> list[dict]:
    counts: dict[str, dict] = {}
    for r in t.by_status(Status.NEEDS_MANUAL, Status.FAILED):
        for q in row_list(r, "unanswered"):
            m = re.match(r"(.*?)\s*\[(\w+)\]\s*—\s*(.*)$", q)
            label, kind, why = (m.group(1), m.group(2), m.group(3)) if m else (q, "?", "")
            label = label.strip().rstrip("*✱ ").strip()
            d = counts.setdefault(label.lower(), {"question": label, "type": kind, "jobs": 0, "why": why,
                                                  "example_job": f"{r['title']} — {r['company']}"})
            d["jobs"] += 1
    return sorted(counts.values(), key=lambda d: -d["jobs"])


def job_rows(rows) -> list[dict]:
    return [{"key": r["key"], "score": round(r["score"] or 0, 2), "link": r["apply_url"] or r["url"],
             "title": r["title"], "company": r["company"],
             "type": r["work_type"], "location": r["location"], "site": f"{r['source']} → {r['ats'] or '?'}",
             "why": why_bucket(r) if r["status"] in ("needs_manual", "failed") else (r["reason"] or ""),
             "status": r["status"]} for r in rows]


def mark_applied(key: str) -> None:
    from src.content.profile import Profile
    from src.notify.discord import DiscordNotifier
    from src.pipeline import Pipeline, _safe
    s, t = settings(), tracker()
    ev = s.evidence_dir / _safe(key)
    ev.mkdir(parents=True, exist_ok=True)
    (ev / "assist_page.txt").write_text("Submitted by you (marked in the interface).\n", encoding="utf-8")
    t.set_status(key, Status.APPLIED, "you confirmed submission (interface)", method="user_confirmed",
                 evidence_dir=str(ev), follow_up_days=s.follow_up_days)
    notifier = DiscordNotifier((s.raw.get("notifications") or {}).get("discord"))
    notifier.applied(t.get(key))
    Pipeline(s, t, Profile.load(), sources_cfg={}, notifier=notifier).interview_prep(key)


def ensure_letter(key: str) -> str:
    from src.content.cover_letter import CoverLetterWriter
    from src.content.profile import Profile
    from src.pipeline import row_to_job
    s, t = settings(), tracker()
    r = t.get(key)
    if r["cover_letter"]:
        return r["cover_letter"]
    text = CoverLetterWriter(Profile.load(), s.llm_model).write(row_to_job(r), row_list(r, "matched_skills")).text
    t.update_fields(key, cover_letter=text)
    return text


def win_task(action: str) -> str:
    if os.name != "nt":
        return "Scheduled task control is only available on Windows."
    cmds = {"state": 'Get-ScheduledTask -TaskName "JOB-PLY" | Select-Object -ExpandProperty State',
            "enable": 'Enable-ScheduledTask -TaskName "JOB-PLY" | Out-Null; "Enabled"',
            "disable": 'Disable-ScheduledTask -TaskName "JOB-PLY" | Out-Null; "Disabled"',
            "run": 'Start-ScheduledTask -TaskName "JOB-PLY"; "Started"'}
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", cmds[action]], capture_output=True,
                             text=True, timeout=20, creationflags=NO_WINDOW)
        return (out.stdout or out.stderr).strip() or "?"
    except Exception as e:
        return f"error: {e}"


# ============================================================================ sidebar: runs
s = settings()
with st.sidebar:
    st.title("💼 JOB-PLY")
    live = s.profile_reviewed
    st.caption(("🟢 **Live** — real submissions on" if live else "🟡 **Not live** — dry runs only") +
               f" · cap {s.daily_cap}/day")
    busy = running()
    if busy:
        import time as _time
        st.warning(f"⏳ Running: **{busy.get('what')}** (started "
                   f"{_time.strftime('%d %b %H:%M', _time.localtime(busy['started']))})")
    st.subheader("Run")
    c1, c2 = st.columns(2)
    if c1.button("▶ Run now", width="stretch", disabled=bool(busy) or not live,
                 help="Find jobs, write cover letters, auto-submit where possible"):
        spawn(["run"]); st.toast("Run started"); st.rerun()
    if c2.button("🧪 Dry run", width="stretch", disabled=bool(busy),
                 help="Same, but fills forms WITHOUT submitting"):
        spawn(["run", "--dry-run"]); st.toast("Dry run started"); st.rerun()
    c3, c4 = st.columns(2)
    if c3.button("🔎 Find jobs", width="stretch", disabled=bool(busy), help="Search all sites only"):
        spawn(["discover"]); st.rerun()
    if c4.button("♻ Re-check", width="stretch", disabled=bool(busy),
                 help="Re-apply filters to filtered-out jobs (after changing filters)"):
        spawn(["refilter"]); st.rerun()
    if st.button("✉ Write cover letters", width="stretch", disabled=bool(busy)):
        spawn(["prepare"]); st.rerun()

    @st.fragment(run_every=3)
    def live_log():
        text = tail(LOG_UI, 25)
        if text:
            st.caption("Last run output")
            st.code(text[-3000:], language="text")
    live_log()

t = tracker()
counts = t.counts()
tab_dash, tab_apply, tab_queue, tab_apps, tab_answers, tab_settings = st.tabs(
    ["📊 Dashboard", "🔗 Apply", "🗂 Job queue", "✅ My applications", "❓ Answers", "⚙ Settings & logs"])

# ============================================================================ dashboard
with tab_dash:
    m = st.columns(6)
    m[0].metric("Applied today", t.count_applied_today())
    m[1].metric("Applied (all)", counts.get("applied", 0) + counts.get("responded", 0)
                + counts.get("interview", 0) + counts.get("rejected", 0) + counts.get("offer", 0))
    m[2].metric("Interviews", counts.get("interview", 0))
    m[3].metric("Need you", counts.get("needs_manual", 0) + counts.get("failed", 0))
    m[4].metric("Auto-apply queue", counts.get("ready", 0))
    m[5].metric("Filtered out", counts.get("filtered_out", 0))

    left, right = st.columns([3, 2])
    with left:
        st.subheader("Why jobs couldn't be auto-applied")
        bd = breakdown(t.by_status(Status.NEEDS_MANUAL, Status.FAILED))
        if bd:
            st.dataframe([{"reason": k, "jobs": v} for k, v in bd.items()], hide_index=True, width="stretch")
        else:
            st.info("Nothing waiting for you.")
        st.subheader("Follow-ups due")
        due = t.follow_ups_due()
        if due:
            st.dataframe([{"key": r["key"], "title": r["title"], "company": r["company"],
                           "applied": (r["applied_at"] or "")[:10]} for r in due], hide_index=True,
                         width="stretch")
        else:
            st.caption("None due.")
    with right:
        st.subheader("Recent activity")
        ev = t.recent_events(20)
        if ev:
            for e in ev:
                icon = {"applied": "✅", "needs_manual": "⚠️", "failed": "❌", "interview": "🎉", "ready": "🟦",
                        "shortlisted": "⭐", "skipped": "⏭", "rejected": "✖"}.get(e["to_status"], "•")
                st.markdown(f"{icon} `{e['ts'][5:16]}` **{e['title'] or ''}** — {e['company'] or ''}  \n"
                            f"<span style='opacity:.7'>{e['to_status']}: {(e['detail'] or '')[:90]}</span>",
                            unsafe_allow_html=True)
        else:
            st.caption("No activity yet.")

# ============================================================================ apply (click-through list)
with tab_apply:
    todo = t.by_status(Status.NEEDS_MANUAL, Status.FAILED)
    st.caption(f"{len(todo)} jobs need you · best matches first · click **Open job ↗**, apply on the site, "
               f"then tick it off here. Your CV: `{s.cv_path}`")
    fa, fb = st.columns([3, 1])
    aq = fa.text_input("Filter", "", key="apply_filter", placeholder="title, company or location")
    if aq:
        al = aq.lower()
        todo = [r for r in todo if al in f"{r['title']} {r['company']} {r['location']}".lower()]
    per = 25
    pages = max(1, (len(todo) + per - 1) // per)
    page_no = fb.number_input("Page", 1, pages, 1, key="apply_page")
    for r in todo[(page_no - 1) * per: page_no * per]:
        with st.container(border=True):
            c1, c2, c3, c4, c5 = st.columns([5.4, 1.6, 1.3, 1.8, 1.2])
            c1.markdown(f"**{r['title']}** — {r['company']}  \n"
                        f"<span style='opacity:.75'>{r['location'] or ''} · {r['work_type'] or ''} · "
                        f"match {(r['score'] or 0):.2f} · {why_bucket(r)}</span>", unsafe_allow_html=True)
            c2.link_button("Open job ↗", r["apply_url"] or r["url"], width="stretch")
            letter = r["cover_letter"] or ""
            if letter:
                c3.download_button("✉ Letter", letter, file_name=f"cover_letter_{re.sub(r'[^A-Za-z0-9]+', '_', r['company'] or 'job')}.txt",
                                   key=f"al_{r['key']}", width="stretch")
            else:
                if c3.button("✉ Write", key=f"aw_{r['key']}", width="stretch"):
                    ensure_letter(r["key"]); st.rerun()
            with c4.popover("✅ Applied", width="stretch"):
                st.write("Did you press **Submit** on the employer's site and see their confirmation?")
                if st.button("Yes — record it", key=f"aa_{r['key']}", type="primary"):
                    mark_applied(r["key"]); st.rerun()
            if c5.button("⏭ Skip", key=f"as_{r['key']}", width="stretch"):
                t.set_status(r["key"], Status.SKIPPED, "skipped in interface"); st.rerun()
            if row_list(r, "unanswered"):
                st.caption("Form asks: " + " · ".join(q.split(" [")[0] for q in row_list(r, "unanswered")[:3]))

# ============================================================================ job queue
with tab_queue:
    f1, f2, f3 = st.columns([2, 2, 3])
    status_opts = ["needs_manual", "failed", "ready", "shortlisted", "skipped", "filtered_out"]
    chosen = f1.multiselect("Status", status_opts, default=["needs_manual", "failed", "ready"])
    wt = f2.multiselect("Work type", ["Remote", "Hybrid", "On-site", "Unspecified"])
    q = f3.text_input("Search title / company", "")
    rows = t.by_status(*[Status(c) for c in chosen]) if chosen else []
    if wt:
        rows = [r for r in rows if (r["work_type"] or "Unspecified") in wt]
    if q:
        ql = q.lower()
        rows = [r for r in rows if ql in (r["title"] or "").lower() or ql in (r["company"] or "").lower()]
    st.caption(f"{len(rows)} jobs · best matches first · click a row to open it")
    data = job_rows(rows[:500])
    sel = st.dataframe(data, hide_index=True, width="stretch", on_select="rerun",
                       selection_mode="single-row", key="queue_table",
                       column_config={"key": None, "score": st.column_config.ProgressColumn(
                           "match", min_value=0, max_value=1, format="%.2f"),
                           "link": st.column_config.LinkColumn("apply", display_text="Open ↗")})
    picked = sel.selection.rows if sel and hasattr(sel, "selection") else []
    if picked:
        r = t.get(data[picked[0]]["key"])
        st.divider()
        st.subheader(f"{r['title']} — {r['company']}")
        st.caption(f"{r['location'] or ''} · {r['work_type'] or ''} · {r['source']} → {r['ats'] or '?'} · "
                   f"match {(r['score'] or 0):.2f} · status **{r['status']}**")
        if r["reason"]:
            st.info(r["reason"])
        for qn in row_list(r, "unanswered"):
            st.warning(f"Unanswered: {qn}")
        b1, b2, b3, b4, b5 = st.columns(5)
        b1.link_button("🌐 Open job", r["apply_url"] or r["url"], width="stretch")
        if r["ats"] in ATS_AUTO:
            if b2.button("📝 Open pre-filled form", width="stretch",
                         help="Opens the tool's browser with the form filled from your answers. Never submits."):
                spawn(["prefill", r["key"]], log_to=None)
                st.toast("Opening the form in a new browser window…")
        sure = st.checkbox("I pressed Submit on the employer's site and saw their confirmation",
                           key=f"sure_{r['key']}")
        if b3.button("✅ I submitted it", type="primary", width="stretch", key=f"ap_{r['key']}", disabled=not sure):
            mark_applied(r["key"]); st.success("Recorded as applied — Discord notified."); st.rerun()
        if b4.button("⏭ Skip", width="stretch", key=f"sk_{r['key']}"):
            t.set_status(r["key"], Status.SKIPPED, "skipped in interface"); st.rerun()
        if r["status"] == "skipped" and b5.button("↩ Back to queue", width="stretch"):
            t.set_status(r["key"], Status.NEEDS_MANUAL, "restored from skipped"); st.rerun()

        with st.expander("✉ Cover letter", expanded=True):
            letter = r["cover_letter"] or ""
            if not letter and st.button("Write a cover letter for this job"):
                ensure_letter(r["key"]); st.rerun()
            if letter:
                edited = st.text_area("Edit if you like — saved to this job", letter, height=320,
                                      key=f"cl_{r['key']}")
                c1, c2 = st.columns(2)
                if c1.button("💾 Save letter", key=f"save_{r['key']}"):
                    t.update_fields(r["key"], cover_letter=edited); st.success("Saved.")
                c2.download_button("⬇ Download .txt", edited, file_name=f"cover_letter_{r['company']}.txt",
                                   key=f"dl_{r['key']}")
                st.caption(f"Words: {len(edited.split())}")
        with st.expander("Job description"):
            st.write(r["description"] or "_no description stored_")
        with st.expander("History"):
            for e in t.events_for(r["key"]):
                st.text(f"{e['ts']}  {e['from_status'] or '-':>14} → {e['to_status']:<14} {e['detail'] or ''}")

# ============================================================================ my applications
with tab_apps:
    apps = t.by_status(Status.APPLIED, Status.RESPONDED, Status.INTERVIEW, Status.REJECTED, Status.OFFER,
                       order="applied_at DESC")
    st.caption(f"{len(apps)} applications")
    adata = [{"key": r["key"], "applied": (r["applied_at"] or "")[:10], "title": r["title"], "company": r["company"],
              "how": "auto" if r["apply_method"] == "auto" else "you", "status": r["status"],
              "follow up": r["follow_up_date"] or ""} for r in apps]
    asel = st.dataframe(adata, hide_index=True, width="stretch", on_select="rerun",
                        selection_mode="single-row", key="apps_table", column_config={"key": None})
    ap = asel.selection.rows if asel and hasattr(asel, "selection") else []
    if ap:
        r = t.get(adata[ap[0]]["key"])
        st.divider()
        st.subheader(f"{r['title']} — {r['company']}")
        st.link_button("🌐 Job page", r["url"] or r["apply_url"] or "#")
        c1, c2 = st.columns([2, 1])
        new_status = c1.selectbox("Update status", ["applied", "responded", "interview", "rejected", "offer"],
                                  index=["applied", "responded", "interview", "rejected", "offer"].index(r["status"]),
                                  key=f"st_{r['key']}")
        note = c1.text_input("Note (optional)", key=f"note_{r['key']}")
        if c2.button("Save status", key=f"sv_{r['key']}") and new_status != r["status"]:
            t.set_status(r["key"], Status(new_status), note or f"marked {new_status} in interface")
            if new_status == "interview":
                from src.content.profile import Profile
                from src.pipeline import Pipeline
                Pipeline(settings(), t, Profile.load(), sources_cfg={}).interview_prep(r["key"])
            st.rerun()
        if r["confirmation_text"]:
            st.success(f"Employer confirmation: {r['confirmation_text'][:300]}")
        evd = Path(r["evidence_dir"]) if r["evidence_dir"] else None
        if evd and evd.exists():
            imgs = [p for p in ["confirmation.png", "form_filled.png", "assist_after_submit.png"] if (evd / p).exists()]
            for p in imgs[:2]:
                st.image(str(evd / p), caption=p, use_container_width=True)
        prep = s.evidence_dir.parent / "interview_prep"
        guides = list(prep.glob(f"{re.sub(r'[^A-Za-z0-9]+', '_', r['company'] or '')[:60]}*.md")) if prep.exists() else []
        with st.expander("📘 Interview prep", expanded=r["status"] == "interview"):
            if guides:
                st.markdown(guides[0].read_text(encoding="utf-8"))
            else:
                st.caption("No guide yet — set status to *interview* to create one.")

# ============================================================================ answers
with tab_answers:
    st.subheader("Questions employers asked that you haven't answered yet")
    st.caption("Add a rule once and every future form asking the same thing is filled automatically. "
               "Only put answers that are true — they are sent to employers as facts.")
    summ = unanswered_summary(t)
    if summ:
        st.dataframe(summ, hide_index=True, width="stretch")
        with st.form("add_rule"):
            st.markdown("**Add a rule**")
            q_pick = st.selectbox("Question", [d["question"] for d in summ])
            words = re.sub(r"[^a-z0-9 ]", " ", q_pick.lower()).split()
            keep = [w for w in words if w not in {"you", "your", "the", "a", "an", "do", "did", "have", "are", "is",
                                                  "what", "which", "please", "of", "to", "in", "or", "and"}]
            suggestion = ".*".join((keep or words)[:4])
            c1, c2 = st.columns(2)
            rid = c1.text_input("Rule id", re.sub(r"[^a-z0-9]+", "_", " ".join((keep or words)[:4]))[:40])
            pat = c2.text_input("Pattern (words from the question, regex allowed)", suggestion)
            ans = st.text_input("Your answer (exact option text for choice questions, or TODO)", "TODO")
            if st.form_submit_button("Add rule to the top of answers.yaml"):
                if not re.search(pat, q_pick, re.I):
                    st.error("That pattern doesn't match the question — try fewer / different words.")
                else:
                    err = add_rule(rid, pat, ans)
                    if err:
                        st.error(err)
                    else:
                        st.success("Rule added. Next run will use it.")
    else:
        st.info("No unanswered questions right now.")

    st.divider()
    st.subheader("Edit config files")
    fname = st.selectbox("File", ["answers.yaml", "user_profile.yaml", "filters.yaml", "sources.yaml", "settings.yaml"])
    content = (CONFIG / fname).read_text(encoding="utf-8")
    edited = st.text_area(fname, content, height=460, key=f"cfg_{fname}")
    c1, c2 = st.columns([1, 4])
    if c1.button("💾 Validate & save", key=f"savecfg_{fname}"):
        err = save_config(fname, edited)
        if err:
            st.error(err)
        else:
            st.success(f"Saved (previous version kept as {fname}.bak).")
    c2.caption("Files are checked before saving; a broken file is never written.")

# ============================================================================ settings & logs
with tab_settings:
    st.subheader("Switches")
    c1, c2, c3, c4 = st.columns(4)
    go_live = c1.toggle("Live (real submissions)", value=s.profile_reviewed,
                        help="Off = nothing is ever submitted; dry runs still work")
    headless = c2.toggle("Hide browser during runs", value=s.headless)
    cap = c3.number_input("Daily cap", 1, 50, s.daily_cap)
    ms = c4.number_input("Min match score", 0.0, 1.0, float(s.min_score), step=0.05)
    if st.button("💾 Save switches"):
        p = CONFIG / "settings.yaml"
        for k, v in (("profile_reviewed", go_live), ("headless", headless), ("daily_cap", int(cap)),
                     ("min_score", round(ms, 2))):
            set_scalar(p, k, v)
        st.success("Saved."); st.rerun()

    st.subheader("Scheduled runs (08:45 & 17:45)")
    state = win_task("state")
    st.write(f"Task state: **{state}**")
    d1, d2, d3 = st.columns(3)
    if d1.button("Enable"):
        st.toast(win_task("enable")); st.rerun()
    if d2.button("Disable"):
        st.toast(win_task("disable")); st.rerun()
    if d3.button("Run scheduled task now"):
        st.toast(win_task("run"))

    st.subheader("Connections")
    keys = ["REED_API_KEY", "ADZUNA_APP_ID", "ADZUNA_APP_KEY", "JOOBLE_API_KEY", "ANTHROPIC_API_KEY"]
    st.write(" · ".join(f"{'✅' if env(k) else '⬜'} {k}" for k in keys) + " · " +
             f"{'✅' if env('DISCORD_WEBHOOK_URL') or env('DISCORD_APPLICATIONS_WEBHOOK') else '⬜'} Discord")
    cv_ok = s.cv_path and s.cv_path.exists()
    st.write(f"{'✅' if cv_ok else '❌'} CV: `{s.cv_path}`")
    if st.button("Send Discord test"):
        spawn(["test-discord"]); st.toast("Sent — check Discord")

    st.subheader("Log")
    st.code(tail(ROOT / "logs" / "agent.log", 120) or "(empty)", language="text")
