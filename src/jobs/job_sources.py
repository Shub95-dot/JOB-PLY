"""Abstractions and concrete implementations for job boards and APIs (free sources)."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any
import requests
from src.core.models import Job
from src.core.utils import setup_logger, retry

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
        logger.info(f"Fetching jobs from Remotive API: {self.endpoint}")
        try:
            response = requests.get(self.endpoint, timeout=10)
            response.raise_for_status()
            data = response.json()
            raw_jobs = data.get("jobs", [])
            
            jobs = []
            for item in raw_jobs:
                job = Job(
                    title=item.get("title", "Data Analyst"),
                    company=item.get("company_name", "Unknown Company"),
                    location=item.get("candidate_required_location", "Remote"),
                    work_type="Remote" if "remote" in str(item.get("job_type", "")).lower() else "Hybrid",
                    description=item.get("description", ""),
                    url=item.get("url", "https://remotive.com"),
                    source="remotive",
                    posted_date=item.get("publication_date")
                )
                jobs.append(job)
            
            logger.info(f"Fetched {len(jobs)} raw jobs from Remotive.")
            return jobs
        except Exception as e:
            logger.error(f"Failed to fetch jobs from Remotive: {e}")
            return []


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
    if source_type.lower() == "remotive":
        return RemotiveJobSource(**kwargs)
    elif source_type.lower() == "mock":
        return MockJobSource()
    else:
        raise ValueError(f"Unsupported job source type: {source_type}")
