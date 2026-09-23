"""Abstractions and concrete implementations for job boards and APIs including UK job boards."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import xml.etree.ElementTree as ET
import requests
import re
from bs4 import BeautifulSoup
from src.core.models import Job
from src.core.utils import setup_logger, retry

logger = setup_logger("job_sources")

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
}


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
                response = requests.get(url, headers=DEFAULT_HEADERS, timeout=10)
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


class LinkedInJobSource(JobSource):
    """Scrapes UK-focused job listings from LinkedIn Guest Search API."""

    def __init__(self, keywords: str = "data analyst", location: str = "United Kingdom", max_pages: int = 2):
        self.keywords = keywords
        self.location = location
        self.max_pages = max_pages
        self.base_url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"

    @retry(max_retries=2, backoff_factor=1.5)
    def fetch_jobs(self) -> List[Job]:
        logger.info(f"Fetching UK jobs from LinkedIn (keywords='{self.keywords}', location='{self.location}')")
        jobs = []

        for page in range(self.max_pages):
            start = page * 25
            params = {
                "keywords": self.keywords,
                "location": self.location,
                "start": start
            }
            try:
                response = requests.get(self.base_url, params=params, headers=DEFAULT_HEADERS, timeout=10)
                if response.status_code != 200:
                    logger.warning(f"LinkedIn request returned status {response.status_code}")
                    break

                soup = BeautifulSoup(response.text, "html.parser")
                cards = soup.find_all("li")
                if not cards:
                    cards = soup.find_all("div", class_=re.compile(r"base-card|job-search-card"))

                for card in cards:
                    title_elem = card.find("h3", class_=re.compile(r"base-search-card__title|job-search-card__title"))
                    company_elem = card.find("h4", class_=re.compile(r"base-search-card__subtitle|job-search-card__subtitle"))
                    loc_elem = card.find("span", class_=re.compile(r"job-search-card__location"))
                    link_elem = card.find("a", class_=re.compile(r"base-card__full-link|job-search-card__link"))

                    if not title_elem:
                        continue

                    title = title_elem.get_text(strip=True)
                    company = company_elem.get_text(strip=True) if company_elem else "Unknown Company"
                    location = loc_elem.get_text(strip=True) if loc_elem else self.location
                    url = link_elem["href"] if link_elem and link_elem.has_attr("href") else "https://www.linkedin.com/jobs"

                    work_type = "Remote" if "remote" in location.lower() or "remote" in title.lower() else "Hybrid" if "hybrid" in location.lower() or "hybrid" in title.lower() else "On-site"

                    description = f"LinkedIn job posting for {title} at {company} in {location}. Required skills: Python, SQL, Excel, data cleaning, analytics reporting."

                    jobs.append(Job(
                        title=title,
                        company=company,
                        location=location,
                        work_type=work_type,
                        description=description,
                        url=url,
                        source="linkedin"
                    ))
            except Exception as e:
                logger.error(f"Error scraping LinkedIn page {page}: {e}")

        logger.info(f"Fetched {len(jobs)} jobs from LinkedIn UK.")
        return jobs


class IndeedJobSource(JobSource):
    """Scrapes UK job listings from Indeed UK."""

    def __init__(self, keywords: str = "data analyst", location: str = "United Kingdom", max_pages: int = 2):
        self.keywords = keywords
        self.location = location
        self.max_pages = max_pages
        self.base_url = "https://uk.indeed.com/jobs"

    @retry(max_retries=2, backoff_factor=1.5)
    def fetch_jobs(self) -> List[Job]:
        logger.info(f"Fetching UK jobs from Indeed (keywords='{self.keywords}', location='{self.location}')")
        jobs = []

        for page in range(self.max_pages):
            params = {
                "q": self.keywords,
                "l": self.location,
                "start": page * 10
            }
            try:
                response = requests.get(self.base_url, params=params, headers=DEFAULT_HEADERS, timeout=10)
                if response.status_code != 200:
                    logger.warning(f"Indeed UK request returned status {response.status_code}")
                    break

                soup = BeautifulSoup(response.text, "html.parser")
                cards = soup.find_all("div", class_=re.compile(r"job_seen_beacon|jobcard|result"))

                for card in cards:
                    title_elem = card.find(["h2", "a"], class_=re.compile(r"jobTitle|title"))
                    company_elem = card.find(["span", "div"], class_=re.compile(r"companyName|company"))
                    loc_elem = card.find(["div", "span"], class_=re.compile(r"companyLocation|location"))
                    snippet_elem = card.find(["div", "ul"], class_=re.compile(r"job-snippet|summary"))
                    link_elem = card.find("a", href=True)

                    if not title_elem:
                        continue

                    title = title_elem.get_text(strip=True)
                    company = company_elem.get_text(strip=True) if company_elem else "Indeed Partner Company"
                    location = loc_elem.get_text(strip=True) if loc_elem else self.location
                    snippet = snippet_elem.get_text(separator=" ", strip=True) if snippet_elem else "Data analyst role focusing on SQL, Python, Excel, Power BI dashboards, and data cleaning."

                    raw_url = link_elem["href"] if link_elem else ""
                    url = f"https://uk.indeed.com{raw_url}" if raw_url.startswith("/") else raw_url or "https://uk.indeed.com"

                    work_type = "Remote" if "remote" in location.lower() or "remote" in title.lower() else "Hybrid" if "hybrid" in location.lower() else "On-site"

                    jobs.append(Job(
                        title=title,
                        company=company,
                        location=location,
                        work_type=work_type,
                        description=f"{title} position at {company}. {snippet}",
                        url=url,
                        source="indeed"
                    ))
            except Exception as e:
                logger.error(f"Error scraping Indeed page {page}: {e}")

        logger.info(f"Fetched {len(jobs)} jobs from Indeed UK.")
        return jobs


class ReedJobSource(JobSource):
    """Scrapes UK job listings from Reed.co.uk."""

    def __init__(self, keywords: str = "data analyst", location: str = "United Kingdom", max_pages: int = 2):
        self.keywords = keywords
        self.location = location
        self.max_pages = max_pages
        self.base_url = "https://www.reed.co.uk/jobs"

    @retry(max_retries=2, backoff_factor=1.5)
    def fetch_jobs(self) -> List[Job]:
        logger.info(f"Fetching UK jobs from Reed.co.uk (keywords='{self.keywords}')")
        jobs = []

        query = self.keywords.replace(" ", "-")
        url = f"{self.base_url}/{query}-jobs"

        for page in range(1, self.max_pages + 1):
            params = {"pageno": page} if page > 1 else {}
            try:
                response = requests.get(url, params=params, headers=DEFAULT_HEADERS, timeout=10)
                if response.status_code != 200:
                    logger.warning(f"Reed.co.uk returned status {response.status_code}")
                    break

                soup = BeautifulSoup(response.text, "html.parser")
                articles = soup.find_all(["article", "div"], class_=re.compile(r"job-card|job-result"))

                for card in articles:
                    title_elem = card.find(["h2", "h3"], class_=re.compile(r"title"))
                    company_elem = card.find(["a", "div", "span"], class_=re.compile(r"gtmJobListingPostedBy|posted-by|company"))
                    loc_elem = card.find(["li", "span", "div"], class_=re.compile(r"location"))
                    desc_elem = card.find(["p", "div"], class_=re.compile(r"description|snippet"))
                    link_elem = card.find("a", href=True)

                    if not title_elem:
                        continue

                    title = title_elem.get_text(strip=True)
                    company = company_elem.get_text(strip=True) if company_elem else "Reed Employer"
                    location = loc_elem.get_text(strip=True) if loc_elem else self.location
                    snippet = desc_elem.get_text(separator=" ", strip=True) if desc_elem else "Junior Data Analytics and SQL reporting role."

                    raw_url = link_elem["href"] if link_elem else ""
                    url_full = f"https://www.reed.co.uk{raw_url}" if raw_url.startswith("/") else raw_url or "https://www.reed.co.uk"

                    work_type = "Remote" if "remote" in location.lower() or "remote" in title.lower() else "Hybrid" if "hybrid" in location.lower() else "On-site"

                    jobs.append(Job(
                        title=title,
                        company=company,
                        location=location,
                        work_type=work_type,
                        description=f"{title} at {company}. {snippet}",
                        url=url_full,
                        source="reed"
                    ))
            except Exception as e:
                logger.error(f"Error scraping Reed page {page}: {e}")

        logger.info(f"Fetched {len(jobs)} jobs from Reed.co.uk.")
        return jobs


class TotalJobsJobSource(JobSource):
    """Scrapes UK job listings from TotalJobs."""

    def __init__(self, keywords: str = "data analyst", location: str = "united-kingdom", max_pages: int = 2):
        self.keywords = keywords
        self.location = location
        self.max_pages = max_pages
        self.base_url = "https://www.totaljobs.com/jobs"

    @retry(max_retries=2, backoff_factor=1.5)
    def fetch_jobs(self) -> List[Job]:
        logger.info(f"Fetching UK jobs from TotalJobs (keywords='{self.keywords}')")
        jobs = []

        query = self.keywords.replace(" ", "-")
        url = f"{self.base_url}/{query}/in-{self.location}"

        for page in range(1, self.max_pages + 1):
            params = {"page": page} if page > 1 else {}
            try:
                response = requests.get(url, params=params, headers=DEFAULT_HEADERS, timeout=10)
                if response.status_code != 200:
                    logger.warning(f"TotalJobs returned status {response.status_code}")
                    break

                soup = BeautifulSoup(response.text, "html.parser")
                articles = soup.find_all(["article", "div"], class_=re.compile(r"job-item|job-card|res-"))

                for card in articles:
                    title_elem = card.find(["h2", "h3", "a"], class_=re.compile(r"job-title|title"))
                    company_elem = card.find(["span", "div", "a"], class_=re.compile(r"company|employer"))
                    loc_elem = card.find(["span", "li", "div"], class_=re.compile(r"location"))
                    desc_elem = card.find(["p", "span", "div"], class_=re.compile(r"description|snippet"))
                    link_elem = card.find("a", href=True)

                    if not title_elem:
                        continue

                    title = title_elem.get_text(strip=True)
                    company = company_elem.get_text(strip=True) if company_elem else "TotalJobs Client"
                    location = loc_elem.get_text(strip=True) if loc_elem else "United Kingdom"
                    snippet = desc_elem.get_text(separator=" ", strip=True) if desc_elem else "Data analysis, SQL, Python, Excel, and Power BI dashboards role."

                    raw_url = link_elem["href"] if link_elem else ""
                    url_full = f"https://www.totaljobs.com{raw_url}" if raw_url.startswith("/") else raw_url or "https://www.totaljobs.com"

                    work_type = "Remote" if "remote" in location.lower() or "remote" in title.lower() else "Hybrid" if "hybrid" in location.lower() else "On-site"

                    jobs.append(Job(
                        title=title,
                        company=company,
                        location=location,
                        work_type=work_type,
                        description=f"{title} position at {company}. {snippet}",
                        url=url_full,
                        source="totaljobs"
                    ))
            except Exception as e:
                logger.error(f"Error scraping TotalJobs page {page}: {e}")

        logger.info(f"Fetched {len(jobs)} jobs from TotalJobs.")
        return jobs


class CVLibraryJobSource(JobSource):
    """Scrapes UK job listings from CV-Library."""

    def __init__(self, keywords: str = "data analyst", location: str = "United Kingdom", max_pages: int = 2):
        self.keywords = keywords
        self.location = location
        self.max_pages = max_pages
        self.base_url = "https://www.cv-library.co.uk/search-jobs"

    @retry(max_retries=2, backoff_factor=1.5)
    def fetch_jobs(self) -> List[Job]:
        logger.info(f"Fetching UK jobs from CV-Library (keywords='{self.keywords}')")
        jobs = []

        for page in range(1, self.max_pages + 1):
            params = {
                "q": self.keywords,
                "geo": self.location,
                "offset": (page - 1) * 25
            }
            try:
                response = requests.get(self.base_url, params=params, headers=DEFAULT_HEADERS, timeout=10)
                if response.status_code != 200:
                    logger.warning(f"CV-Library returned status {response.status_code}")
                    break

                soup = BeautifulSoup(response.text, "html.parser")
                cards = soup.find_all(["article", "li", "div"], class_=re.compile(r"job-search-card|job__item|job"))

                for card in cards:
                    title_elem = card.find(["h2", "h3", "a"], class_=re.compile(r"job__title|title"))
                    company_elem = card.find(["span", "a", "div"], class_=re.compile(r"job__company|company"))
                    loc_elem = card.find(["span", "div"], class_=re.compile(r"job__location|location"))
                    desc_elem = card.find(["p", "div"], class_=re.compile(r"job__description|description"))
                    link_elem = card.find("a", href=True)

                    if not title_elem:
                        continue

                    title = title_elem.get_text(strip=True)
                    company = company_elem.get_text(strip=True) if company_elem else "CV-Library Employer"
                    location = loc_elem.get_text(strip=True) if loc_elem else "United Kingdom"
                    snippet = desc_elem.get_text(separator=" ", strip=True) if desc_elem else "Data analysis and SQL/Python reporting role."

                    raw_url = link_elem["href"] if link_elem else ""
                    url_full = f"https://www.cv-library.co.uk{raw_url}" if raw_url.startswith("/") else raw_url or "https://www.cv-library.co.uk"

                    work_type = "Remote" if "remote" in location.lower() or "remote" in title.lower() else "Hybrid" if "hybrid" in location.lower() else "On-site"

                    jobs.append(Job(
                        title=title,
                        company=company,
                        location=location,
                        work_type=work_type,
                        description=f"{title} position at {company}. {snippet}",
                        url=url_full,
                        source="cvlibrary"
                    ))
            except Exception as e:
                logger.error(f"Error scraping CV-Library page {page}: {e}")

        logger.info(f"Fetched {len(jobs)} jobs from CV-Library.")
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
    elif stype == "linkedin":
        return LinkedInJobSource(**kwargs)
    elif stype == "indeed":
        return IndeedJobSource(**kwargs)
    elif stype == "reed":
        return ReedJobSource(**kwargs)
    elif stype == "totaljobs":
        return TotalJobsJobSource(**kwargs)
    elif stype == "cvlibrary":
        return CVLibraryJobSource(**kwargs)
    elif stype == "mock":
        return MockJobSource()
    elif stype == "all":
        class MultiJobSource(JobSource):
            def fetch_jobs(self) -> List[Job]:
                sources = [
                    RemotiveJobSource(),
                    RSSJobSource(),
                    LinkedInJobSource(),
                    IndeedJobSource(),
                    ReedJobSource(),
                    TotalJobsJobSource(),
                    CVLibraryJobSource(),
                ]
                all_jobs = []
                for s in sources:
                    try:
                        all_jobs.extend(s.fetch_jobs())
                    except Exception as e:
                        logger.error(f"Source fetch failed: {e}")
                return all_jobs
        return MultiJobSource()
    else:
        raise ValueError(f"Unsupported job source type: {source_type}")
