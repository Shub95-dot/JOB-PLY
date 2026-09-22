"""Abstractions and concrete implementations for job boards and APIs (free sources)."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any
import requests
from src.core.models import Job
from src.core.utils import setup_logger, retry

import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup

logger = setup_logger("job_sources")


class JobSource(ABC):
    """Abstract base class for job sources."""

    @abstractmethod
    def fetch_jobs(self) -> List[Job]:
        """Fetch raw job postings and convert to domain Job models."""
        pass


class RemotiveJobSource(JobSource):
    """Fetches public remote data roles from Remotive free API."""

    def __init__(self, endpoint: str = "https://remotive.com/api/remote-jobs?category=data"):
        self.endpoint = endpoint

    @retry(max_retries=2, backoff_factor=1.5)
    def fetch_jobs(self) -> List[Job]:
        logger.info(f"Fetching real jobs from Remotive API: {self.endpoint}")
        try:
            response = requests.get(self.endpoint, timeout=12)
            response.raise_for_status()
            data = response.json()
            raw_jobs = data.get("jobs", [])
            
            jobs = []
            for item in raw_jobs:
                # Strip HTML tags from raw Remotive description
                raw_desc = item.get("description", "")
                clean_desc = BeautifulSoup(raw_desc, "html.parser").get_text(separator=" ") if "<" in raw_desc else raw_desc

                job = Job(
                    title=item.get("title", "Data Analyst"),
                    company=item.get("company_name", "Unknown Company"),
                    location=item.get("candidate_required_location", "Remote"),
                    work_type="Remote" if "remote" in str(item.get("job_type", "")).lower() or not item.get("candidate_required_location") else "Hybrid",
                    description=clean_desc,
                    url=item.get("url", "https://remotive.com"),
                    source="remotive",
                    posted_date=item.get("publication_date")
                )
                jobs.append(job)
            
            logger.info(f"Fetched {len(jobs)} real jobs from Remotive API.")
            return jobs
        except Exception as e:
            logger.error(f"Failed to fetch jobs from Remotive: {e}")
            return []


class RSSJobSource(JobSource):
    """Fetches public data roles from RSS feeds (e.g. WeWorkRemotely, Jobspire)."""

    def __init__(self, rss_urls: Optional[List[str]] = None):
        self.rss_urls = rss_urls or [
            "https://weworkremotely.com/categories/remote-back-end-programming-jobs.rss",
            "https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss"
        ]

    @retry(max_retries=2, backoff_factor=1.5)
    def fetch_jobs(self) -> List[Job]:
        logger.info(f"Fetching real jobs from {len(self.rss_urls)} RSS feeds.")
        jobs = []
        for url in self.rss_urls:
            try:
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                response = requests.get(url, headers=headers, timeout=10)
                response.raise_for_status()
                
                root = ET.fromstring(response.text)
                channel = root.find("channel")
                if channel is None:
                    continue

                for item in channel.findall("item"):
                    title_elem = item.find("title")
                    link_elem = item.find("link")
                    desc_elem = item.find("description")
                    pub_date = item.find("pubDate")

                    title_text = title_elem.text if title_elem is not None and title_elem.text else "Data Role"
                    link_text = link_elem.text if link_elem is not None and link_elem.text else "https://weworkremotely.com"
                    raw_desc = desc_elem.text if desc_elem is not None and desc_elem.text else ""

                    clean_desc = BeautifulSoup(raw_desc, "html.parser").get_text(separator=" ") if "<" in raw_desc else raw_desc

                    # Extract company name from title pattern e.g. "Company: Title" or "Title at Company"
                    company = "Remote Tech Co"
                    if ":" in title_text:
                        parts = title_text.split(":", 1)
                        company = parts[0].strip()
                        title_text = parts[1].strip()
                    elif " is hiring " in title_text.lower():
                        parts = title_text.lower().split(" is hiring ")
                        company = parts[0].strip().title()

                    jobs.append(Job(
                        title=title_text,
                        company=company,
                        location="Remote",
                        work_type="Remote",
                        description=clean_desc,
                        url=link_text,
                        source="rss",
                        posted_date=pub_date.text if pub_date is not None else None
                    ))
            except Exception as e:
                logger.warning(f"Failed to fetch RSS feed {url}: {e}")

        logger.info(f"Fetched {len(jobs)} real jobs from RSS feeds.")
        return jobs


class MockJobSource(JobSource):
    """Mock job source returning predefined test jobs."""

    def fetch_jobs(self) -> List[Job]:
        logger.info("Fetching jobs from MockJobSource.")
        mock_data = [
            {
                "title": "Junior Data Analyst",
                "company": "TechMetrics Ltd",
                "location": "London, UK",
                "work_type": "Hybrid",
                "description": "We are seeking a Junior Data Analyst to join our team. Required skills: Python, SQL, Excel, data cleaning, EDA, Power BI dashboards. Entry level / graduate position with full mentorship and training.",
                "url": "https://example.com/jobs/jr-data-analyst-1",
                "source": "mock"
            },
            {
                "title": "Graduate Data Scientist",
                "company": "AI Insights Labs",
                "location": "Remote",
                "work_type": "Remote",
                "description": "Graduate Data Scientist position for passionate analytics candidates. Strong foundation in Python, SQL, statistics, ML basics, and exploratory data analysis required. Includes structured training program.",
                "url": "https://example.com/jobs/grad-ds-2",
                "source": "mock"
            },
            {
                "title": "Senior Data Engineering Manager",
                "company": "Global Cloud Corp",
                "location": "London, UK",
                "work_type": "On-site",
                "description": "Senior Lead Manager role managing 15 engineers. Requires 10+ years of experience with Spark, AWS, Kubernetes.",
                "url": "https://example.com/jobs/senior-manager-3",
                "source": "mock"
            },
            {
                "title": "Business Analyst (Data & Insights)",
                "company": "Fintech Solutions",
                "location": "London, UK",
                "work_type": "Hybrid",
                "description": "Data-heavy Business Analyst role focusing on SQL reporting, Tableau dashboards, data cleaning, and insights generation for junior analysts.",
                "url": "https://example.com/jobs/ba-data-4",
                "source": "mock"
            }
        ]
        return [Job(**item) for item in mock_data]


def get_job_source(source_type: str = "remotive", **kwargs: Any) -> JobSource:
    """Factory function to instantiate job source strategy."""
    stype = source_type.lower()
    if stype == "remotive":
        return RemotiveJobSource(**kwargs)
    elif stype == "rss":
        return RSSJobSource(**kwargs)
    elif stype == "mock":
        return MockJobSource()
    elif stype == "all":
        # Aggregated multi-source
        class MultiJobSource(JobSource):
            def fetch_jobs(self) -> List[Job]:
                rem = RemotiveJobSource().fetch_jobs()
                rss = RSSJobSource().fetch_jobs()
                return rem + rss
        return MultiJobSource()
    else:
        raise ValueError(f"Unsupported job source type: {source_type}")

