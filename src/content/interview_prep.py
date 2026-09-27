"""Interview-prep guide for a job, built only from the real posting and your profile.

Generated when an application is VERIFIED (and again when you `mark ... interview`), saved to
data/interview_prep/<Company>_<Role>.md, and announced on Discord.

Sections: what they want (sentences pulled from the posting), your evidence for each skill
(which of YOUR projects used it), gaps to close, topics to revise per skill, STAR stories from
your projects, and questions to ask them.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Optional

from src.content.profile import Profile

REVISION = {
    "sql": ["JOIN types and when rows multiply", "GROUP BY + HAVING", "window functions (ROW_NUMBER, LAG, running totals)",
            "CTEs vs subqueries", "NULL handling in joins and aggregates"],
    "python": ["pandas merge / groupby / pivot_table", "cleaning: missing values, types, duplicates",
               "writing a small function + a test", "reading CSV/Excel/SQL into pandas"],
    "excel": ["XLOOKUP / INDEX-MATCH", "PivotTables and slicers", "SUMIFS / COUNTIFS", "data validation, conditional formatting"],
    "power bi": ["star schema: facts vs dimensions", "DAX: CALCULATE, filter context, time intelligence",
                 "measures vs calculated columns", "Power Query transformations", "row-level security basics"],
    "tableau": ["LOD expressions (FIXED/INCLUDE)", "calculated fields", "dashboard actions and filters"],
    "statistics": ["mean vs median, spread, outliers", "hypothesis tests and p-values in plain English",
                   "confidence intervals", "correlation vs causation"],
    "a/b testing": ["sample size and power", "choosing a primary metric", "novelty effects and peeking"],
    "machine learning": ["train/test split and leakage", "precision vs recall trade-off", "cross-validation",
                         "explaining a model to non-technical people"],
    "regression": ["interpreting coefficients", "R² vs RMSE", "multicollinearity"],
    "forecasting": ["trend/seasonality", "baseline forecasts", "evaluating on a time-based split"],
    "etl": ["incremental vs full loads", "data-quality checks", "idempotent pipelines"],
    "dashboards": ["choosing the right chart", "KPI definitions agreed with stakeholders", "designing for the audience"],
    "data visualisation": ["choosing the right chart", "avoiding misleading axes", "one message per chart"],
    "data visualization": ["choosing the right chart", "avoiding misleading axes", "one message per chart"],
    "data cleaning": ["documenting every cleaning rule", "deduplication", "validating against source totals"],
    "dbt": ["models, refs and tests", "incremental models"],
    "snowflake": ["warehouses vs databases", "clustering and cost basics"],
    "bigquery": ["partitioning and cost", "standard SQL differences"],
    "azure": ["Azure Data Factory / Synapse at a high level"],
    "aws": ["S3 + Athena/Redshift at a high level"],
    "git": ["branch, commit, pull request workflow"],
}

WANT_RX = re.compile(r"\b(you will|you'll|responsib|day[- ]to[- ]day|duties|role involves|you'll be|key tasks)\b", re.I)
NEED_RX = re.compile(r"\b(experience (with|in|of)|knowledge of|proficien|familiar|essential|required|must have|"
                     r"skills?:|ability to|degree|qualification|desirable|nice to have|bonus)\b", re.I)

QUESTIONS = [
    "What would a great first 90 days look like in this role?",
    "Which tools and data sources would I use day to day?",
    "Who are the main stakeholders for the team's analysis, and how do they request work?",
    "How is the quality of the team's reporting checked before it goes out?",
    "What training or mentoring is available for someone at the start of their analytics career?",
]


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\s[•·▪●-]\s|\n+", text or "")
    return [re.sub(r"\s+", " ", p).strip(" -•") for p in parts if 25 <= len(p.strip()) <= 260]


def _pick(sents: list[str], rx: re.Pattern, n: int) -> list[str]:
    out, seen = [], set()
    for s in sents:
        k = s.lower()[:60]
        if rx.search(s) and k not in seen:
            out.append(s)
            seen.add(k)
        if len(out) >= n:
            break
    return out


def _safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")[:60]


def build(row, profile: Profile, have: list[str], missing: list[str]) -> str:
    desc = row["description"] or ""
    sents = _sentences(desc)
    wants = _pick(sents, WANT_RX, 8)
    needs = _pick(sents, NEED_RX, 8)
    canon = {s.lower(): s for s in profile.skills}
    name = lambda s: canon.get(s.lower(), s.upper() if len(s) <= 3 else s.title())

    evidence = []
    for s in have:
        projs = [p.get("short_title") or p["title"] for p in profile.projects
                 if any(s.lower() == t.lower() or s.lower() in t.lower() for t in p.get("tech", []))]
        evidence.append(f"- **{name(s)}** — " + (", ".join(projs) if projs else "listed in your skills; prepare a concrete example"))

    topics = []
    for s in list(have) + list(missing):
        for t in REVISION.get(s.lower(), []):
            topics.append(f"- {name(s)}: {t}")

    stars = []
    for p in profile.projects:
        res = p.get("results", []) if p.get("verified") else []
        stars.append(
            f"### {p.get('short_title') or p['title']}\n"
            f"- **Situation/Task:** what problem the project addressed and why it mattered\n"
            f"- **Action:** I {p.get('summary', '').rstrip('.')}.\n"
            f"- **Result:** " + ("; ".join(r.rstrip('.') for r in res) + "." if res else
                                 "_add a real, checkable outcome before the interview_") + "\n"
            f"- **Tools:** {', '.join(p.get('tech', []))}")

    pubs = profile.data.get("publications", [])
    pub_line = ""
    if pubs:
        pb = pubs[0]
        pub_line = (f"\n> Mention your publication: *{pb['title']}* — {pb['journal']}, {pb['date']}, "
                    f"DOI {pb.get('doi', '')}. Be ready to explain the leakage-safe SMOTE choice in one minute.\n")

    lines = [
        f"# Interview prep — {row['title']} at {row['company']}",
        "",
        f"- **Location / type:** {row['location'] or '—'} ({row['work_type'] or 'Unspecified'})",
        f"- **Posting:** {row['url'] or ''}",
        f"- **Applied:** {(row['applied_at'] or '')[:10] or '—'} via {row['source']} → {row['ats'] or '—'}",
        f"- **Relevance score:** {(row['score'] or 0):.2f} (ranking only)",
        f"- **Generated:** {date.today().isoformat()}",
        pub_line,
        "## What they want you to do (from the posting)",
        *(f"- {w}" for w in wants), *(["- _posting didn't list duties clearly — reread it on the site_"] if not wants else []),
        "",
        "## What they ask for (from the posting)",
        *(f"- {n}" for n in needs), *(["- _no explicit requirements found in the text we have_"] if not needs else []),
        "",
        "## Your evidence, skill by skill",
        *(evidence or ["- _no overlapping skills detected — read the posting carefully_"]),
        "",
        "## Gaps to close before the interview",
        *([f"- **{name(m)}** — not in your profile. Do a short tutorial and be honest that you're learning it."
           for m in missing] or ["- none detected"]),
        "",
        "## Topics to revise",
        *(topics or ["- SQL: joins, GROUP BY, window functions", "- Explaining an analysis to a non-technical audience"]),
        "",
        "## STAR stories from your projects",
        *stars,
        "",
        "## Questions to ask them",
        *(f"- {q}" for q in QUESTIONS),
        "",
        "## Before the call",
        f"- Re-read the posting at {row['url'] or 'the link above'} and the company's latest news / annual report",
        "- Prepare a 60-second introduction: MSc → published research → why this role",
        "- Have one example ready of working accurately under pressure from your operational roles",
    ]
    return "\n".join(lines).replace("\n\n\n", "\n\n") + "\n"


def write(row, profile: Profile, have: list[str], missing: list[str], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{_safe(row['company'] or 'company')}_{_safe(row['title'] or 'role')}.md"
    path.write_text(build(row, profile, have, missing), encoding="utf-8")
    return path


def summary(row, have: list[str], missing: list[str], path: Path) -> dict:
    return {"title": row["title"], "company": row["company"], "url": row["url"], "path": str(path),
            "have": have, "missing": missing}


def topics_for(skills: list[str]) -> list[str]:
    out: list[str] = []
    for s in skills:
        out += REVISION.get(s.lower(), [])[:2]
    return out[:6]


def maybe(row, profile: Profile, out_dir: Path, have: list[str], missing: list[str]) -> Optional[dict]:
    if row is None:
        return None
    p = write(row, profile, have, missing, out_dir)
    return summary(row, have, missing, p)
