"""Hard filters. Every rejection has a human-readable reason, stored in the tracker."""
from __future__ import annotations

import re
from typing import Any

from src.core.config import load_yaml
from src.core.models import FilterResult, Job

_EN_STOP = {"the", "and", "to", "of", "a", "in", "for", "with", "you", "our", "we", "is", "will",
            "on", "be", "are", "as", "your", "this", "an", "or", "have", "work", "team", "data"}
_FOREIGN_STOP = {  # German, French, Dutch, Spanish, Italian function words
    "und", "der", "die", "das", "wir", "mit", "für", "sie", "ist", "ein", "eine", "einen", "unser", "unsere", "auf", "bei",
    "et", "les", "des", "pour", "nous", "vous", "une", "avec", "est", "dans", "sur",
    "en", "het", "een", "wij", "voor", "je", "zijn", "van",
    "y", "los", "las", "para", "con", "una", "el", "il", "della", "per", "che"}
_WORD = re.compile(r"[a-zà-ÿ]+", re.I)
_YEARS = re.compile(
    r"(?:(?:minimum|at least|min\.?)\s+(?:of\s+)?)?(\d{1,2})\s*(?:\+|plus)?\s*(?:-|–|to)?\s*(\d{1,2})?\s*\+?\s*(?:years?|yrs?)"
    r"(?:'|’)?\s*(?:of\s+)?(?:\w+\s+){0,4}?(?:experience|exp\b)", re.I)


class JobFilter:
    def __init__(self, cfg: dict[str, Any] | None = None):
        c = cfg if cfg is not None else load_yaml("filters.yaml")
        low = lambda k: [x.lower() for x in c.get(k, [])]
        self.include_titles = low("include_titles")
        self.exclude_title_words = low("exclude_title_words")
        self.exclude_title_phrases = low("exclude_title_phrases")
        self.exclude_companies = low("exclude_companies")
        self.exclude_description_phrases = low("exclude_description_phrases")
        self.locations_ok = low("uk_locations")
        self.uk_only_sources = set(c.get("uk_only_sources", ["reed", "adzuna", "jooble"]))
        self.remote_ok_tokens = low("remote_ok_locations")
        self.remote_reject_region_locked = bool(c.get("remote_reject_region_locked", True))
        self.max_years = int(c.get("max_years_experience", 2))
        self.skills = low("skills")
        self.work_types = [w.lower() for w in c.get("allowed_work_types", ["remote", "hybrid", "on-site", "unspecified"])]
        self.needs_sponsorship = c.get("needs_visa_sponsorship")  # None = don't filter on it
        self.no_sponsor_phrases = low("no_sponsorship_phrases")

    # --------------------------------------------------------------- title only (cheap, pre-enrichment)
    def title_ok(self, job: Job) -> FilterResult:
        t = f" {job.title.lower()} "
        for co in self.exclude_companies:
            if co and co in job.company.lower():
                return FilterResult(accepted=False, reason=f"excluded company '{job.company}'")
        for ph in self.exclude_title_phrases:
            if ph in t:
                return FilterResult(accepted=False, reason=f"title contains '{ph}'")
        for w in self.exclude_title_words:
            if re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", t):
                return FilterResult(accepted=False, reason=f"seniority/unsuitable word '{w}' in title")
        if not any(p in t for p in self.include_titles):
            return FilterResult(accepted=False, reason="title not a target data role")
        return FilterResult(accepted=True, reason="title ok")

    # --------------------------------------------------------------- full check
    def evaluate(self, job: Job) -> FilterResult:
        r = self.title_ok(job)
        if not r.accepted:
            return r
        desc = job.description or ""
        dl = desc.lower()

        if not self._is_english(job.title + " " + desc):
            return FilterResult(accepted=False, reason="posting not in English")

        loc_problem = self._location_ok(job)
        if loc_problem:
            return FilterResult(accepted=False, reason=loc_problem)

        if job.work_type.lower() not in self.work_types:
            return FilterResult(accepted=False, reason=f"work type {job.work_type} not allowed")

        for ph in self.exclude_description_phrases:
            if ph in dl:
                return FilterResult(accepted=False, reason=f"description contains '{ph}'")

        yrs = self.required_years(desc)
        if yrs is not None and yrs > self.max_years:
            return FilterResult(accepted=False, reason=f"asks for {yrs}+ years' experience")

        if self.needs_sponsorship is True:
            for ph in self.no_sponsor_phrases:
                if ph in dl:
                    return FilterResult(accepted=False, reason=f"no visa sponsorship ('{ph}')")

        skills = sorted({s for s in self.skills if re.search(rf"(?<![a-z]){re.escape(s)}(?![a-z])", dl)})
        return FilterResult(accepted=True, reason="passed all filters", matched_skills=skills)

    # --------------------------------------------------------------- helpers
    def required_years(self, text: str) -> int | None:
        """Minimum years of experience the posting asks for (None if not stated)."""
        mins = []
        for m in _YEARS.finditer(text):
            lo = int(m.group(1))
            if lo <= 20:
                mins.append(lo)
        return min(mins) if mins else None

    def _location_ok(self, job: Job) -> str | None:
        """Returns a rejection reason, or None if the location is acceptable.

        Remote            -> any country, as long as the posting doesn't restrict hiring to
                             regions that exclude the UK (e.g. "US only", "LATAM").
        Hybrid / On-site  -> must be in the UK.
        """
        loc = (job.location or "").lower()
        uk_source = job.source in self.uk_only_sources
        is_uk = uk_source or any(re.search(rf"(?<![a-z]){re.escape(k)}(?![a-z])", loc) for k in self.locations_ok)
        wt = job.work_type
        if wt == "Unspecified":
            wt = "Remote" if re.search(r"\bremote\b|anywhere|worldwide", loc) and not is_uk else "On-site"
        if wt in ("Hybrid", "On-site"):
            return None if is_uk else f"{wt} role outside the UK ('{job.location}')"
        # Remote
        bare = re.sub(r"\b(remote|fully|100%|only|job|position)\b|[()\-–,/:|]", " ", loc).strip()
        if is_uk or not bare or any(re.search(rf"(?<![a-z]){re.escape(t)}(?![a-z])", loc) for t in self.remote_ok_tokens):
            return None
        if self.remote_reject_region_locked:
            return f"remote but hiring restricted to '{job.location}' (not UK / worldwide)"
        return None

    @staticmethod
    def _is_english(text: str) -> bool:
        words = [w.lower() for w in _WORD.findall(text[:3000])]
        if len(words) < 15:
            return True
        en = sum(w in _EN_STOP for w in words)
        other = sum(w in _FOREIGN_STOP for w in words)
        return en >= other and en / len(words) >= 0.08
