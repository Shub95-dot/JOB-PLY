"""Worldwide REMOTE job boards with public feeds/APIs, plus Jooble (UK aggregator, free key).

Each board's terms ask that you link back to them and don't hammer them: every board is fetched
at most once per run, and the posting URL (their page) is kept as `url`.
Apply links usually lead to the employer's ATS; if that's Greenhouse/Lever/Ashby the job is
auto-submittable, otherwise it goes to assist mode.
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET

from src.core.config import env
from src.core.models import Job
from src.jobs.sources.base import JobSource, SourceError, html_to_text, infer_work_type

log = logging.getLogger("sources")


class RemoteOKSource(JobSource):
    """https://remoteok.com/api — first array element is a legal notice (skipped)."""
    name = "remoteok"
    URL = "https://remoteok.com/api"

    def __init__(self, tags: list[str] | None = None, session=None):
        super().__init__(session)
        self.tags = tags or ["data", "analyst"]

    def fetch(self) -> list[Job]:
        out: dict[str, Job] = {}
        for tag in self.tags:
            data = self.get_json(self.URL, params={"tag": tag})
            for r in data if isinstance(data, list) else []:
                if not isinstance(r, dict) or "id" not in r or "position" not in r:
                    continue
                jid = str(r["id"])
                out[jid] = Job(
                    source="remoteok", source_id=jid, title=r.get("position", ""), company=r.get("company", ""),
                    location=r.get("location") or "Worldwide", description=html_to_text(r.get("description")),
                    url=r.get("url") or f"https://remoteok.com/remote-jobs/{jid}",
                    apply_url=r.get("apply_url") or r.get("url"), posted_date=r.get("date"), work_type="Remote",
                    salary=f"${r['salary_min']:,}–${r['salary_max']:,}" if r.get("salary_min") and r.get("salary_max") else None)
        log.info("remoteok: %d jobs", len(out))
        return list(out.values())


class HimalayasSource(JobSource):
    """https://himalayas.app/jobs/api/search — `locationRestrictions` empty means worldwide."""
    name = "himalayas"
    URL = "https://himalayas.app/jobs/api/search"

    def __init__(self, queries: list[str] | None = None, pages: int = 3, session=None):
        super().__init__(session)
        self.queries = queries or ["data analyst", "data scientist", "business intelligence"]
        self.pages = pages

    def fetch(self) -> list[Job]:
        out: dict[str, Job] = {}
        for q in self.queries:
            for page in range(1, self.pages + 1):
                try:
                    data = self.get_json(self.URL, params={"q": q, "page": page})
                except SourceError as e:
                    log.warning("himalayas: %s", e)
                    break
                jobs = data.get("jobs", [])
                for r in jobs:
                    jid = str(r.get("guid") or r.get("applicationLink") or r.get("title"))
                    restr = r.get("locationRestrictions") or []
                    loc = ", ".join(x if isinstance(x, str) else x.get("name", "") for x in restr) or "Worldwide"
                    out[jid] = Job(
                        source="himalayas", source_id=jid[-80:], title=r.get("title", ""),
                        company=r.get("companyName", ""), location=loc,
                        description=html_to_text(r.get("description") or r.get("excerpt")),
                        url=r.get("guid") or r.get("applicationLink", ""), apply_url=r.get("applicationLink"),
                        posted_date=str(r.get("pubDate") or ""), work_type="Remote")
                if len(jobs) < 20:
                    break
        log.info("himalayas: %d jobs", len(out))
        return list(out.values())


class JobicySource(JobSource):
    """https://jobicy.com/api/v2/remote-jobs — `jobGeo` gives the hiring region."""
    name = "jobicy"
    URL = "https://jobicy.com/api/v2/remote-jobs"

    def __init__(self, tags: list[str] | None = None, session=None):
        super().__init__(session)
        self.tags = tags or ["data analyst", "data science"]

    def fetch(self) -> list[Job]:
        out: dict[str, Job] = {}
        for tag in self.tags:
            data = self.get_json(self.URL, params={"count": 50, "tag": tag})
            for r in data.get("jobs", []):
                jid = str(r.get("id"))
                out[jid] = Job(
                    source="jobicy", source_id=jid, title=html_to_text(r.get("jobTitle")),
                    company=r.get("companyName", ""), location=r.get("jobGeo") or "Anywhere",
                    description=html_to_text(r.get("jobDescription") or r.get("jobExcerpt")),
                    url=r.get("url", ""), apply_url=r.get("url"), posted_date=r.get("pubDate"), work_type="Remote")
        log.info("jobicy: %d jobs", len(out))
        return list(out.values())


class WorkingNomadsSource(JobSource):
    """https://www.workingnomads.com/api/exposed_jobs/ — full feed, filtered by category."""
    name = "workingnomads"
    URL = "https://www.workingnomads.com/api/exposed_jobs/"
    CATEGORIES = ("data", "analytics", "business intelligence")

    def fetch(self) -> list[Job]:
        data = self.get_json(self.URL)
        jobs = []
        for r in data if isinstance(data, list) else []:
            cat = (r.get("category_name") or "").lower()
            if not any(c in cat or c in (r.get("tags") or "").lower() for c in self.CATEGORIES):
                continue
            url = r.get("url", "")
            jobs.append(Job(
                source="workingnomads", source_id=url.rstrip("/").split("/")[-1] or r.get("title", ""),
                title=r.get("title", ""), company=r.get("company_name", ""), location=r.get("location") or "Anywhere",
                description=html_to_text(r.get("description")), url=url, apply_url=url,
                posted_date=r.get("pub_date"), work_type="Remote"))
        log.info("workingnomads: %d data jobs", len(jobs))
        return jobs


class WeWorkRemotelySource(JobSource):
    """We Work Remotely public RSS. Titles are 'Company: Role'; <region> gives eligibility."""
    name = "weworkremotely"
    FEEDS = ["https://weworkremotely.com/remote-jobs.rss"]

    def fetch(self) -> list[Job]:
        jobs = []
        for feed in self.FEEDS:
            try:
                r = self.session.get(feed, timeout=20)
                r.raise_for_status()
                root = ET.fromstring(r.content)
            except Exception as e:
                log.warning("weworkremotely: %s", e)
                continue
            for it in root.iter("item"):
                raw = (it.findtext("title") or "").strip()
                company, _, title = raw.partition(":") if ":" in raw else ("", "", raw)
                link = (it.findtext("link") or "").strip()
                jobs.append(Job(
                    source="weworkremotely", source_id=link.rstrip("/").split("/")[-1] or raw,
                    title=title.strip(), company=company.strip(),
                    location=(it.findtext("region") or "Anywhere in the World").strip(),
                    description=html_to_text(it.findtext("description")), url=link, apply_url=link,
                    posted_date=it.findtext("pubDate"), work_type="Remote"))
        log.info("weworkremotely: %d jobs", len(jobs))
        return jobs


class ArbeitnowSource(JobSource):
    """https://www.arbeitnow.com/api/job-board-api — Europe-focused; only `remote: true` jobs kept."""
    name = "arbeitnow"
    URL = "https://www.arbeitnow.com/api/job-board-api"

    def __init__(self, pages: int = 3, session=None):
        super().__init__(session)
        self.pages = pages

    def fetch(self) -> list[Job]:
        jobs = []
        for page in range(1, self.pages + 1):
            data = self.get_json(self.URL, params={"page": page})
            for r in data.get("data", []):
                if not r.get("remote"):
                    continue
                jobs.append(Job(
                    source="arbeitnow", source_id=r.get("slug", ""), title=r.get("title", ""),
                    company=r.get("company_name", ""), location=r.get("location") or "Remote (Europe)",
                    description=html_to_text(r.get("description")), url=r.get("url", ""), apply_url=r.get("url"),
                    posted_date=str(r.get("created_at") or ""), work_type="Remote"))
            if not data.get("links", {}).get("next"):
                break
        log.info("arbeitnow: %d remote jobs", len(jobs))
        return jobs


class JoobleSource(JobSource):
    """Jooble UK aggregator — free key from https://jooble.org/api/about (POST API)."""
    name = "jooble"

    def __init__(self, searches: list[dict], api_key: str | None = None, session=None):
        super().__init__(session)
        self.searches = searches
        self.key = api_key or env("JOOBLE_API_KEY")

    def fetch(self) -> list[Job]:
        if not self.key:
            log.warning("jooble: JOOBLE_API_KEY not set — skipping")
            return []
        out: dict[str, Job] = {}
        for s in self.searches:
            try:
                r = self.session.post(f"https://uk.jooble.org/api/{self.key}", timeout=20,
                                      json={"keywords": s["keywords"], "location": s.get("location") or "United Kingdom"})
                r.raise_for_status()
                data = r.json()
            except Exception as e:
                log.warning("jooble: %s", e)
                continue
            for j in data.get("jobs", []):
                jid = str(j.get("id"))
                title, loc, desc = html_to_text(j.get("title")), j.get("location", ""), html_to_text(j.get("snippet"))
                out[jid] = Job(
                    source="jooble", source_id=jid, title=title, company=j.get("company", ""), location=loc,
                    description=desc, url=j.get("link", ""), apply_url=j.get("link"), salary=j.get("salary") or None,
                    posted_date=j.get("updated"), work_type=infer_work_type(title, loc, desc, j.get("type", "")))
        log.info("jooble: %d jobs", len(out))
        return list(out.values())
