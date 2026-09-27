"""UK job aggregators with official APIs: Reed and Adzuna (+ Remotive for remote roles).

Neither Reed nor Adzuna offers an "apply" API. Their jobs are routed either to the
ATS submitter (when the employer's apply link turns out to be Greenhouse/Lever/Ashby)
or to assist mode, where you click submit yourself.
"""
from __future__ import annotations

import logging
from typing import Optional

from src.core.config import env
from src.core.models import Job
from src.jobs.sources.base import JobSource, SourceError, html_to_text, infer_work_type

log = logging.getLogger("sources")


class ReedSource(JobSource):
    """https://www.reed.co.uk/developers/jobseeker — free key; HTTP basic auth, key as username."""
    name = "reed"
    BASE = "https://www.reed.co.uk/api/1.0"

    def __init__(self, searches: list[dict], api_key: Optional[str] = None, max_per_search: int = 100,
                 fetch_details: bool = True, session=None):
        super().__init__(session)
        self.searches = searches
        self.api_key = api_key or env("REED_API_KEY")
        self.max_per_search = max_per_search
        self.fetch_details = fetch_details

    def fetch(self) -> list[Job]:
        if not self.api_key:
            log.warning("reed: REED_API_KEY not set — skipping (get one free at reed.co.uk/developers)")
            return []
        auth = (self.api_key, "")
        out: dict[str, Job] = {}
        for s in self.searches:
            params = {
                "keywords": s["keywords"],
                "locationName": s.get("location", ""),
                "distanceFromLocation": s.get("distance_miles", 20),
                "resultsToTake": min(100, self.max_per_search),
                "resultsToSkip": 0,
            }
            if s.get("graduate"):
                params["graduate"] = "true"
            if s.get("min_salary"):
                params["minimumSalary"] = s["min_salary"]
            data = self.get_json(f"{self.BASE}/search", params=params, auth=auth)
            for r in data.get("results", []):
                jid = str(r.get("jobId"))
                if jid in out:
                    continue
                job = Job(
                    source="reed", source_id=jid,
                    title=r.get("jobTitle", "").strip(),
                    company=(r.get("employerName") or "").strip(),
                    location=r.get("locationName") or "",
                    description=html_to_text(r.get("jobDescription")),
                    url=r.get("jobUrl") or f"https://www.reed.co.uk/jobs/{jid}",
                    salary=_salary(r.get("minimumSalary"), r.get("maximumSalary")),
                    posted_date=r.get("date"),
                )
                out[jid] = job
        jobs = list(out.values())
        log.info("reed: %d unique jobs from %d searches", len(jobs), len(self.searches))
        return jobs

    def enrich(self, job: Job) -> Job:
        """Full description + external apply URL (call only for jobs that pass the title filter)."""
        if not self.fetch_details or not self.api_key:
            return job
        try:
            d = self.get_json(f"{self.BASE}/jobs/{job.source_id}", auth=(self.api_key, ""))
        except SourceError as e:
            log.warning("reed details %s: %s", job.source_id, e)
            return job
        job.description = html_to_text(d.get("jobDescription")) or job.description
        job.apply_url = d.get("externalUrl") or None
        job.work_type = infer_work_type(job.title, job.location, job.description)
        return job


class AdzunaSource(JobSource):
    """https://developer.adzuna.com — free app_id/app_key. Descriptions are truncated (~500 chars)."""
    name = "adzuna"
    BASE = "https://api.adzuna.com/v1/api/jobs/gb/search"

    def __init__(self, searches: list[dict], app_id: Optional[str] = None, app_key: Optional[str] = None,
                 pages: int = 2, max_days_old: int = 14, session=None):
        super().__init__(session)
        self.searches = searches
        self.app_id = app_id or env("ADZUNA_APP_ID")
        self.app_key = app_key or env("ADZUNA_APP_KEY")
        self.pages = pages
        self.max_days_old = max_days_old

    def fetch(self) -> list[Job]:
        if not (self.app_id and self.app_key):
            log.warning("adzuna: ADZUNA_APP_ID / ADZUNA_APP_KEY not set — skipping")
            return []
        out: dict[str, Job] = {}
        for s in self.searches:
            for page in range(1, self.pages + 1):
                params = {
                    "app_id": self.app_id, "app_key": self.app_key,
                    "what": s["keywords"], "where": s.get("location", ""),
                    "distance": int(s.get("distance_miles", 20) * 1.61),
                    "results_per_page": 50, "max_days_old": self.max_days_old,
                    "content-type": "application/json",
                }
                if s.get("what_exclude"):
                    params["what_exclude"] = s["what_exclude"]
                data = self.get_json(f"{self.BASE}/{page}", params=params)
                results = data.get("results", [])
                for r in results:
                    jid = str(r.get("id"))
                    if jid in out:
                        continue
                    title = html_to_text(r.get("title"))
                    loc = (r.get("location") or {}).get("display_name", "")
                    desc = html_to_text(r.get("description"))
                    out[jid] = Job(
                        source="adzuna", source_id=jid, title=title,
                        company=(r.get("company") or {}).get("display_name", "") or "",
                        location=loc, description=desc,
                        url=r.get("redirect_url", ""), apply_url=r.get("redirect_url"),
                        salary=_salary(r.get("salary_min"), r.get("salary_max")),
                        posted_date=r.get("created"),
                        work_type=infer_work_type(title, loc, desc),
                    )
                if len(results) < 50:
                    break
        jobs = list(out.values())
        log.info("adzuna: %d unique jobs", len(jobs))
        return jobs


class RemotiveSource(JobSource):
    """Public remote-jobs API (worldwide). Region eligibility is checked by the filter."""
    name = "remotive"
    URL = "https://remotive.com/api/remote-jobs"
    UK_OK = ("uk", "united kingdom", "europe", "emea", "worldwide", "anywhere", "gmt", "global")

    def __init__(self, category: str = "data", session=None):
        super().__init__(session)
        self.category = category

    def fetch(self) -> list[Job]:
        data = self.get_json(self.URL, params={"category": self.category})
        jobs = []
        for r in data.get("jobs", []):
            jobs.append(Job(
                source="remotive", source_id=str(r.get("id")),
                title=r.get("title", ""), company=r.get("company_name", ""),
                location=r.get("candidate_required_location") or "Remote",
                description=html_to_text(r.get("description")),
                url=r.get("url", ""), apply_url=r.get("url"),
                salary=r.get("salary") or None, posted_date=r.get("publication_date"),
                work_type="Remote",
            ))
        log.info("remotive: %d remote jobs", len(jobs))
        return jobs


def _salary(lo, hi) -> Optional[str]:
    if not lo and not hi:
        return None
    if lo and hi and lo != hi:
        return f"£{int(lo):,}–£{int(hi):,}"
    return f"£{int(lo or hi):,}"
