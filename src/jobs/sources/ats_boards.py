"""Public job-board APIs of the three ATSs we can submit to: Greenhouse, Lever, Ashby.

These APIs are published by the ATS vendors for exactly this purpose (listing a company's
open roles). Each needs the company's board token, e.g. `monzo` in
job-boards.greenhouse.io/monzo. Tokens come from config/sources.yaml and are also
auto-discovered from Reed/Adzuna apply links (stored in the tracker's `boards` table).
"""
from __future__ import annotations

import logging

from src.core.models import Job
from src.jobs.sources.base import JobSource, SourceError, html_to_text, infer_work_type

log = logging.getLogger("sources")


class GreenhouseSource(JobSource):
    name = "greenhouse"
    API = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"

    def __init__(self, tokens: list[str], session=None):
        super().__init__(session)
        self.tokens = tokens

    def fetch(self) -> list[Job]:
        jobs: list[Job] = []
        for token in self.tokens:
            try:
                data = self.get_json(self.API.format(token=token), params={"content": "true"})
            except SourceError as e:
                log.warning("greenhouse/%s: %s", token, e)
                continue
            company = (data.get("meta") or {}).get("company_name") or token.replace("-", " ").title()
            for r in data.get("jobs", []):
                jid = str(r["id"])
                loc = (r.get("location") or {}).get("name", "")
                desc = html_to_text(r.get("content"))
                jobs.append(Job(
                    source="greenhouse", source_id=f"{token}/{jid}",
                    title=r.get("title", ""), company=r.get("company_name") or company,
                    location=loc, description=desc,
                    url=r.get("absolute_url") or f"https://job-boards.greenhouse.io/{token}/jobs/{jid}",
                    apply_url=f"https://job-boards.greenhouse.io/{token}/jobs/{jid}",
                    posted_date=r.get("updated_at"),
                    work_type=infer_work_type(r.get("title", ""), loc),
                ))
        log.info("greenhouse: %d jobs from %d boards", len(jobs), len(self.tokens))
        return jobs

    def questions(self, token: str, job_id: str) -> list[dict]:
        """Application questions (label, required, field names/types) — used as a pre-flight check."""
        data = self.get_json(f"{self.API.format(token=token)}/{job_id}", params={"questions": "true"})
        return data.get("questions", [])


class LeverSource(JobSource):
    name = "lever"
    API = {"global": "https://api.lever.co/v0/postings/{site}", "eu": "https://api.eu.lever.co/v0/postings/{site}"}

    def __init__(self, sites: list[str], session=None):
        super().__init__(session)
        self.sites = sites

    def fetch(self) -> list[Job]:
        jobs: list[Job] = []
        for site in self.sites:
            data = None
            for region, api in self.API.items():
                try:
                    data = self.get_json(api.format(site=site), params={"mode": "json"})
                    break
                except SourceError:
                    continue
            if data is None:
                log.warning("lever/%s: board not found (global or EU)", site)
                continue
            for r in data:
                cats = r.get("categories") or {}
                loc = cats.get("location") or ", ".join(cats.get("allLocations") or [])
                lists = " ".join(f"{x.get('text','')} {html_to_text(x.get('content'))}" for x in r.get("lists") or [])
                desc = " ".join([r.get("descriptionPlain") or html_to_text(r.get("description")), lists,
                                 r.get("additionalPlain") or ""]).strip()
                jobs.append(Job(
                    source="lever", source_id=f"{site}/{r['id']}",
                    title=r.get("text", ""), company=site.replace("-", " ").title(),
                    location=loc, description=desc,
                    url=r.get("hostedUrl", ""), apply_url=r.get("applyUrl") or (r.get("hostedUrl", "") + "/apply"),
                    work_type={"remote": "Remote", "hybrid": "Hybrid", "on-site": "On-site"}.get(
                        (r.get("workplaceType") or "").lower(), infer_work_type(r.get("text", ""), loc)),
                ))
        log.info("lever: %d jobs from %d sites", len(jobs), len(self.sites))
        return jobs


class AshbySource(JobSource):
    name = "ashby"
    API = "https://api.ashbyhq.com/posting-api/job-board/{org}"

    def __init__(self, orgs: list[str], session=None):
        super().__init__(session)
        self.orgs = orgs

    def fetch(self) -> list[Job]:
        jobs: list[Job] = []
        for org in self.orgs:
            try:
                data = self.get_json(self.API.format(org=org))
            except SourceError as e:
                log.warning("ashby/%s: %s", org, e)
                continue
            for r in data.get("jobs", []):
                if r.get("isListed") is False:
                    continue
                loc = r.get("location") or ""
                wt = (r.get("workplaceType") or "").lower()
                jobs.append(Job(
                    source="ashby", source_id=f"{org}/{r['id']}",
                    title=r.get("title", ""), company=org.replace("-", " ").title(),
                    location=loc, description=r.get("descriptionPlain") or html_to_text(r.get("descriptionHtml")),
                    url=r.get("jobUrl", ""), apply_url=r.get("applyUrl") or (r.get("jobUrl", "") + "/application"),
                    posted_date=r.get("publishedAt"),
                    work_type={"remote": "Remote", "hybrid": "Hybrid", "onsite": "On-site"}.get(
                        wt, "Remote" if r.get("isRemote") else infer_work_type(r.get("title", ""), loc)),
                ))
        log.info("ashby: %d jobs from %d orgs", len(jobs), len(self.orgs))
        return jobs
