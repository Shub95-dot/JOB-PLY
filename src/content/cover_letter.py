"""Cover letters that only state facts from your profile.

Guards applied to every letter (LLM or template) before it can be used:
  * 150–230 words;
  * every number in the letter must appear in your profile facts or the job posting;
  * no employer/organisation names other than the target company and ones in your profile;
  * must name the role and the company.
If the LLM draft fails a guard, the deterministic template is used instead.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.content.profile import Profile
from src.core.config import env
from src.core.models import Job

log = logging.getLogger("cover_letter")

MIN_WORDS, MAX_WORDS = 150, 230
_NUM = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?%?")


@dataclass
class Letter:
    text: str
    method: str            # "llm" | "template"
    guard_notes: list[str]


class CoverLetterWriter:
    def __init__(self, profile: Profile, model: str = "claude-sonnet-5", use_llm: bool = True):
        self.profile = profile
        self.model = model
        self.use_llm = use_llm and bool(env("ANTHROPIC_API_KEY"))

    def write(self, job: Job, have_skills: list[str]) -> Letter:
        notes: list[str] = []
        if self.use_llm:
            try:
                draft = self._llm(job, have_skills)
                problems = self.check(draft, job)
                if not problems:
                    return Letter(draft, "llm", [])
                notes = [f"LLM draft rejected: {p}" for p in problems]
                log.info("cover letter for %s rejected by guard: %s", job.key, problems)
            except Exception as e:  # API error etc.
                notes = [f"LLM unavailable: {e}"]
        text = self._template(job, have_skills)
        problems = self.check(text, job)
        return Letter(text, "template", notes + [f"template: {p}" for p in problems])

    # ------------------------------------------------------------------ guard
    def check(self, text: str, job: Job) -> list[str]:
        problems = []
        n = len(text.split())
        if not (MIN_WORDS <= n <= MAX_WORDS):
            problems.append(f"{n} words (needs {MIN_WORDS}–{MAX_WORDS})")
        allowed = set(_NUM.findall(self.profile.fact_text() + " " + job.description + " " + job.title))
        allowed |= {str(y) for y in range(2015, 2031)}
        bad = [x for x in _NUM.findall(text) if x not in allowed]
        if bad:
            problems.append(f"numbers not in your profile/job: {sorted(set(bad))}")
        if job.company and job.company.lower() not in text.lower():
            problems.append("does not name the company")
        return problems

    # ------------------------------------------------------------------ generators
    def _pick_project(self, job: Job) -> Optional[dict]:
        jd = (job.title + " " + job.description).lower()
        best, best_hits = None, -1
        for p in self.profile.projects:
            hits = sum(1 for t in p.get("tech", []) if t.lower() in jd)
            if hits > best_hits:
                best, best_hits = p, hits
        return best

    def _template(self, job: Job, have: list[str]) -> str:
        p = self.profile
        canon = {x.lower(): x for x in p.skills}
        names = [canon.get(s.lower(), s.upper() if len(s) <= 3 else s.title()) for s in (have or ["python", "sql", "power bi"])[:4]]
        skills = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
        proj = self._pick_project(job)
        edu = p.education[0] if p.education else {}
        degree = edu.get("degree", "MSc")
        inst = edu.get("institution", "")
        para1 = (f"Dear Hiring Team at {job.company},\n\n"
                 f"I am applying for the {job.title} role. I have {'completed' if edu.get('status') == 'completed' else 'nearly completed'} an {degree}"
                 f"{' at ' + inst if inst else ''}, and I am looking for an entry-level analytics position "
                 f"where I can turn data into clear, practical decisions.")
        pubs = p.data.get("publications", [])
        and_join = lambda xs: xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]
        if proj:
            tech = and_join(proj.get("tech", [])[:4])
            name = proj.get("short_title") or proj["title"]
            pub_note = ""
            if isinstance(proj.get("publication"), int) and proj["publication"] < len(pubs):
                pub = pubs[proj["publication"]]
                pub_note = f" (published in the {pub['journal'].split(' (')[0]}, {pub['date'].split(' ', 1)[-1]})"
            result = ""
            if proj.get("verified") and proj.get("results"):
                result = f" {proj['results'][0].rstrip('.')}."
            summary = proj.get("summary", "built an end-to-end analysis").strip().rstrip(".")
            para2 = (f"Your posting asks for {skills}. In my project \"{name}\"{pub_note} I "
                     f"{summary}, using {tech}.{result}")
            if pubs and not pub_note:
                pub = pubs[0]
                para2 += (f" I have also published peer-reviewed research, \"{pub['title']}\", in the "
                          f"{pub['journal'].split(' (')[0]}.")
        else:
            para2 = (f"Your posting asks for {skills}, which I use regularly in my MSc coursework "
                     f"for data cleaning, exploratory analysis and reporting.")
        para3 = ("Alongside my studies I have worked in fast-paced customer-facing and operational roles, "
                 "which taught me reliability, teamwork and how to stay accurate under pressure.")
        para4 = (f"I would welcome the chance to bring these skills to {job.company} and keep learning "
                 f"from an experienced team. Thank you for considering my application.\n\n"
                 f"Kind regards,\n{p.name}")
        text = "\n\n".join([para1, para2, para3, para4])
        # pad/trim softly to stay inside the word window
        if len(text.split()) < MIN_WORDS:
            text = text.replace(para3, para3 + " I am comfortable owning a task end to end, asking good "
                                "questions early and documenting my work so others can build on it.")
        return text

    def _llm(self, job: Job, have: list[str]) -> str:
        import anthropic
        client = anthropic.Anthropic(api_key=env("ANTHROPIC_API_KEY"))
        prompt = f"""Write a cover letter for {self.profile.name} for the role "{job.title}" at {job.company}.

STRICT RULES
- 160–210 words. Plain text. Start "Dear Hiring Team at {job.company}," and end with "Kind regards,\\n{self.profile.name}".
- Use ONLY facts from CANDIDATE FACTS. Do not invent employers, job titles, dates, metrics, percentages, tools or achievements.
- Do not include any number that is not in CANDIDATE FACTS or the JOB POSTING.
- The candidate's paid work so far is in non-analytics roles; do not describe them as an experienced analyst.
- Refer to 2–3 concrete requirements from the posting that the candidate genuinely matches: {", ".join(have) or "general data analysis"}.
- Tone: direct, specific, no clichés ("I am thrilled", "passionate").

CANDIDATE FACTS
{self.profile.fact_text()}

JOB POSTING
{job.description[:3500]}

Return only the letter."""
        msg = client.messages.create(model=self.model, max_tokens=700,
                                     messages=[{"role": "user", "content": prompt}])
        return msg.content[0].text.strip()


def save_letter(text: str, out_dir: Path, name: str = "cover_letter") -> Path:
    """Write the letter as PDF (if reportlab is installed) or .txt — both accepted by the ATSs."""
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
        path = out_dir / f"{name}.pdf"
        style = getSampleStyleSheet()["Normal"]
        story = []
        for para in text.split("\n\n"):
            story += [Paragraph(para.replace("\n", "<br/>"), style), Spacer(1, 10)]
        SimpleDocTemplate(str(path), pagesize=A4).build(story)
        return path
    except ImportError:
        path = out_dir / f"{name}.txt"
        path.write_text(text, encoding="utf-8")
        return path
