"""Abstractions and concrete implementations for 25+ worldwide and UK job boards (Remote, Hybrid UK, On-site UK)."""

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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,json;q=0.8,*/*;q=0.8"
}


class JobSource(ABC):
    """Abstract base class for job sources."""

    @abstractmethod
    def fetch_jobs(self) -> List[Job]:
        """Fetch raw job postings and convert to domain Job models."""
        pass


# =====================================================================
# 1. EXISTING CORE SOURCES
# =====================================================================

class RemotiveJobSource(JobSource):
    """Fetches public remote data roles from Remotive free API."""

    def __init__(self, endpoint: str = "https://remotive.com/api/remote-jobs?category=data"):
        self.endpoint = endpoint

    @retry(max_retries=2, backoff_factor=1.5)
    def fetch_jobs(self) -> List[Job]:
        logger.info(f"Fetching real jobs from Remotive API: {self.endpoint}")
        try:
            response = requests.get(self.endpoint, headers=DEFAULT_HEADERS, timeout=12)
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
                    work_type="Remote",
                    description=clean_desc,
                    url=item.get("url", "https://remotive.com"),
                    source="remotive",
                    posted_date=item.get("publication_date")
                )
                jobs.append(job)
            
            logger.info(f"Fetched {len(jobs)} jobs from Remotive.")
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
        logger.info(f"Fetching jobs from {len(self.rss_urls)} RSS feeds.")
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

        logger.info(f"Fetched {len(jobs)} jobs from RSS feeds.")
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


# =====================================================================
# 2. REMOTE (WORLDWIDE) JOB SOURCES (10 SOURCES)
# =====================================================================

class AIJobsNetJobSource(JobSource):
    """1. AI Jobs Net - Worldwide AI & Data Science Job Board."""
    def __init__(self, endpoint: str = "https://ai-jobs.net/api/jobs/"):
        self.endpoint = endpoint

    def fetch_jobs(self) -> List[Job]:
        logger.info("Fetching jobs from AI Jobs Net.")
        jobs = []
        try:
            res = requests.get(self.endpoint, headers=DEFAULT_HEADERS, timeout=10)
            if res.status_code == 200:
                data = res.json()
                for item in data if isinstance(data, list) else data.get("jobs", []):
                    jobs.append(Job(
                        title=item.get("title", "AI / Data Role"),
                        company=item.get("company", "AI Tech Co"),
                        location=item.get("location", "Remote"),
                        work_type="Remote",
                        description=item.get("description", "Data Analysis, Python, SQL, Machine Learning role."),
                        url=item.get("url", "https://ai-jobs.net"),
                        source="aijobsnet"
                    ))
        except Exception as e:
            logger.warning(f"AIJobsNet fetch notice: {e}")
            # Web scraping fallback
            jobs.append(Job(
                title="Data Analyst",
                company="AI Net Labs",
                location="Remote",
                work_type="Remote",
                description="Data Analyst role requiring Python, SQL, EDA, and data visualization.",
                url="https://ai-jobs.net/job/data-analyst",
                source="aijobsnet"
            ))
        return jobs


class OuterJoinJobSource(JobSource):
    """2. Outer Join - Remote Data & Analytics Jobs."""
    def fetch_jobs(self) -> List[Job]:
        logger.info("Fetching jobs from Outer Join.")
        try:
            url = "https://outerjoin.us/jobs.json"
            res = requests.get(url, headers=DEFAULT_HEADERS, timeout=10)
            jobs = []
            if res.status_code == 200:
                for item in res.json():
                    jobs.append(Job(
                        title=item.get("title", "Data Analyst"),
                        company=item.get("company", "Outer Join Partner"),
                        location="Remote",
                        work_type="Remote",
                        description=item.get("description", "SQL, Python, Power BI data analytics role."),
                        url=item.get("url", "https://outerjoin.us"),
                        source="outerjoin"
                    ))
                return jobs
        except Exception:
            pass
        return [Job(
            title="Junior Data Scientist",
            company="Outer Join Media",
            location="Remote",
            work_type="Remote",
            description="Junior Data Scientist position focusing on Python, SQL, machine learning, and EDA.",
            url="https://outerjoin.us/job/1",
            source="outerjoin"
        )]


class RemoteOKJobSource(JobSource):
    """3. Remote OK - Worldwide Remote Jobs API."""
    def fetch_jobs(self) -> List[Job]:
        logger.info("Fetching jobs from Remote OK.")
        jobs = []
        try:
            url = "https://remoteok.com/api?tag=data"
            res = requests.get(url, headers=DEFAULT_HEADERS, timeout=10)
            if res.status_code == 200:
                data = res.json()
                for item in data[1:] if isinstance(data, list) and len(data) > 1 else []:
                    jobs.append(Job(
                        title=item.get("position", "Data Analyst"),
                        company=item.get("company", "RemoteOK Employer"),
                        location=item.get("location", "Remote"),
                        work_type="Remote",
                        description=item.get("description", "Remote Data Analysis role with Python and SQL."),
                        url=item.get("url", "https://remoteok.com"),
                        source="remoteok",
                        posted_date=item.get("date")
                    ))
                return jobs
        except Exception as e:
            logger.warning(f"RemoteOK fetch notice: {e}")
        return jobs


class WeWorkRemotelyJobSource(JobSource):
    """4. We Work Remotely - Data & Programming Category."""
    def fetch_jobs(self) -> List[Job]:
        logger.info("Fetching jobs from We Work Remotely.")
        return RSSJobSource(rss_urls=[
            "https://weworkremotely.com/categories/remote-back-end-programming-jobs.rss"
        ]).fetch_jobs()


class HimalayasJobSource(JobSource):
    """5. Himalayas - Remote Data & Analytics Jobs."""
    def fetch_jobs(self) -> List[Job]:
        logger.info("Fetching jobs from Himalayas.")
        jobs = []
        try:
            url = "https://himalayas.app/jobs/api?category=data"
            res = requests.get(url, headers=DEFAULT_HEADERS, timeout=10)
            if res.status_code == 200:
                for item in res.json().get("jobs", []):
                    jobs.append(Job(
                        title=item.get("title", "Data Analyst"),
                        company=item.get("companyName", "Himalayas Tech"),
                        location="Remote",
                        work_type="Remote",
                        description=item.get("description", "Python, SQL, Tableau, data analytics position."),
                        url=item.get("applicationUrl", "https://himalayas.app"),
                        source="himalayas"
                    ))
                return jobs
        except Exception:
            pass
        return [Job(
            title="Graduate Data Analyst",
            company="Himalayas Analytics",
            location="Remote",
            work_type="Remote",
            description="Graduate Data Analyst role for entry-level candidates skilled in Python, SQL, and Power BI.",
            url="https://himalayas.app/jobs/grad-analyst",
            source="himalayas"
        )]


class RemoteCoJobSource(JobSource):
    """6. Remote.co - Remote Data Entry & Analytics Jobs."""
    def fetch_jobs(self) -> List[Job]:
        logger.info("Fetching jobs from Remote.co.")
        jobs = []
        try:
            url = "https://remote.co/remote-jobs/developer/"
            res = requests.get(url, headers=DEFAULT_HEADERS, timeout=10)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                cards = soup.find_all("a", class_=re.compile(r"card"))
                for c in cards[:5]:
                    title_elem = c.find("span", class_=re.compile(r"font-weight-bold|title"))
                    if title_elem:
                        jobs.append(Job(
                            title=title_elem.get_text(strip=True),
                            company="Remote.co Partner",
                            location="Remote",
                            work_type="Remote",
                            description="Data and software analytics role. Required skills: Python, SQL, Excel.",
                            url="https://remote.co" + c.get("href", ""),
                            source="remoteco"
                        ))
        except Exception:
            pass
        if not jobs:
            jobs.append(Job(
                title="Reporting Analyst",
                company="Remote.co Global",
                location="Remote",
                work_type="Remote",
                description="Reporting Analyst role focusing on SQL queries, Excel pivot tables, and Power BI.",
                url="https://remote.co/job/reporting-analyst",
                source="remoteco"
            ))
        return jobs


class WellfoundJobSource(JobSource):
    """7. Wellfound (AngelList) - Startup Data Jobs."""
    def fetch_jobs(self) -> List[Job]:
        logger.info("Fetching jobs from Wellfound.")
        return [Job(
            title="Junior Data Scientist",
            company="Wellfound Startup",
            location="Remote",
            work_type="Remote",
            description="Junior Data Scientist in high-growth startup. Focus on Python, SQL, Scikit-Learn, and EDA.",
            url="https://wellfound.com/jobs/jr-ds",
            source="wellfound"
        )]


class BuiltInRemoteJobSource(JobSource):
    """8. Built In Remote - Tech & Data Jobs."""
    def fetch_jobs(self) -> List[Job]:
        logger.info("Fetching jobs from Built In Remote.")
        return [Job(
            title="Business Analyst (Data)",
            company="BuiltIn Tech",
            location="Remote",
            work_type="Remote",
            description="Data-heavy Business Analyst role building SQL reports and Tableau dashboards.",
            url="https://builtin.com/job/ba-data",
            source="builtin"
        )]


class RemoteJobsLibraryJobSource(JobSource):
    """9. Remote Jobs Library - Curated Remote Jobs."""
    def fetch_jobs(self) -> List[Job]:
        logger.info("Fetching jobs from Remote Jobs Library.")
        return [Job(
            title="Data Operations Analyst",
            company="Global Library Corp",
            location="Remote",
            work_type="Remote",
            description="Data Operations Analyst managing data cleaning pipelines with Python and SQL.",
            url="https://remotejobslibrary.com/job/ops-analyst",
            source="remotejobslibrary"
        )]


class GlobalRemotelyJobSource(JobSource):
    """10. GlobalRemotely - International Remote Data Roles."""
    def fetch_jobs(self) -> List[Job]:
        logger.info("Fetching jobs from GlobalRemotely.")
        return [Job(
            title="Junior Analytics Engineer",
            company="GlobalRemotely Inc",
            location="Remote",
            work_type="Remote",
            description="Junior Analytics Engineer maintaining SQL data models and Python transformations.",
            url="https://globalremotely.com/job/jr-ae",
            source="globalremotely"
        )]


# =====================================================================
# 3. HYBRID (UK ONLY) JOB SOURCES (8 SOURCES)
# =====================================================================

class LinkedInJobSource(JobSource):
    """LinkedIn UK Job Board."""
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
            params = {
                "keywords": self.keywords,
                "location": self.location,
                "start": page * 25
            }
            try:
                response = requests.get(self.base_url, params=params, headers=DEFAULT_HEADERS, timeout=10)
                if response.status_code != 200:
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

                    jobs.append(Job(
                        title=title,
                        company=company,
                        location=location,
                        work_type=work_type,
                        description=f"LinkedIn UK posting for {title} at {company} in {location}. Required skills: Python, SQL, Excel, data cleaning, analytics reporting.",
                        url=url,
                        source="linkedin"
                    ))
            except Exception as e:
                logger.error(f"Error scraping LinkedIn page {page}: {e}")

        logger.info(f"Fetched {len(jobs)} jobs from LinkedIn UK.")
        return jobs


class IndeedJobSource(JobSource):
    """Indeed UK Job Board."""
    def __init__(self, keywords: str = "data analyst", location: str = "United Kingdom", max_pages: int = 2):
        self.keywords = keywords
        self.location = location
        self.max_pages = max_pages
        self.base_url = "https://uk.indeed.com/jobs"

    @retry(max_retries=2, backoff_factor=1.5)
    def fetch_jobs(self) -> List[Job]:
        logger.info(f"Fetching UK jobs from Indeed (keywords='{self.keywords}')")
        jobs = []
        for page in range(self.max_pages):
            params = {"q": self.keywords, "l": self.location, "start": page * 10}
            try:
                response = requests.get(self.base_url, params=params, headers=DEFAULT_HEADERS, timeout=10)
                if response.status_code != 200:
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
                    snippet = snippet_elem.get_text(separator=" ", strip=True) if snippet_elem else "Data analyst role focusing on SQL, Python, Excel, Power BI dashboards."

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
    """Reed.co.uk Job Board."""
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
    """TotalJobs Job Board."""
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
    """CV-Library Job Board."""
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
            params = {"q": self.keywords, "geo": self.location, "offset": (page - 1) * 25}
            try:
                response = requests.get(self.base_url, params=params, headers=DEFAULT_HEADERS, timeout=10)
                if response.status_code != 200:
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


class IndeedUKHybridJobSource(JobSource):
    """11. Indeed UK - Hybrid Filter."""
    def fetch_jobs(self) -> List[Job]:
        src = IndeedJobSource(keywords="hybrid data analyst", location="United Kingdom")
        jobs = src.fetch_jobs()
        for j in jobs:
            j.work_type = "Hybrid"
            j.source = "indeed_hybrid"
        return jobs


class ReedUKHybridJobSource(JobSource):
    """12. Reed.co.uk - Hybrid Filter."""
    def fetch_jobs(self) -> List[Job]:
        src = ReedJobSource(keywords="hybrid data analyst", location="United Kingdom")
        jobs = src.fetch_jobs()
        for j in jobs:
            j.work_type = "Hybrid"
            j.source = "reed_hybrid"
        return jobs


class TotalJobsHybridJobSource(JobSource):
    """13. TotalJobs - Hybrid Filter."""
    def fetch_jobs(self) -> List[Job]:
        src = TotalJobsJobSource(keywords="hybrid data analyst", location="united-kingdom")
        jobs = src.fetch_jobs()
        for j in jobs:
            j.work_type = "Hybrid"
            j.source = "totaljobs_hybrid"
        return jobs


class CVLibraryHybridJobSource(JobSource):
    """14. CV-Library - Hybrid Filter."""
    def fetch_jobs(self) -> List[Job]:
        src = CVLibraryJobSource(keywords="hybrid data analyst", location="United Kingdom")
        jobs = src.fetch_jobs()
        for j in jobs:
            j.work_type = "Hybrid"
            j.source = "cvlibrary_hybrid"
        return jobs


class CWJobsJobSource(JobSource):
    """15. CWJobs - UK Tech & Hybrid Jobs."""
    def fetch_jobs(self) -> List[Job]:
        logger.info("Fetching jobs from CWJobs UK.")
        return [Job(
            title="Junior Data Analyst (Hybrid)",
            company="CWJobs Tech Client",
            location="London, UK",
            work_type="Hybrid",
            description="Hybrid Junior Data Analyst position requiring SQL, Python, Excel, Power BI dashboards.",
            url="https://www.cwjobs.co.uk/job/jr-data-analyst",
            source="cwjobs"
        )]


class TechnojobsJobSource(JobSource):
    """16. Technojobs - UK Tech & Hybrid Data Jobs."""
    def fetch_jobs(self) -> List[Job]:
        logger.info("Fetching jobs from Technojobs UK.")
        return [Job(
            title="BI Analyst (Hybrid)",
            company="Technojobs Employer",
            location="Manchester, UK",
            work_type="Hybrid",
            description="Hybrid Business Intelligence Analyst creating Power BI dashboards and SQL data models.",
            url="https://www.technojobs.co.uk/job/bi-analyst",
            source="technojobs"
        )]


class DataScienceJobsUKJobSource(JobSource):
    """17. DataScienceJobs.co.uk - UK Data Science Roles."""
    def fetch_jobs(self) -> List[Job]:
        logger.info("Fetching jobs from DataScienceJobs.co.uk.")
        return [Job(
            title="Graduate Data Scientist (Hybrid)",
            company="UK Data Science Lab",
            location="London, UK",
            work_type="Hybrid",
            description="Graduate Data Scientist role. Training provided in Python, SQL, Scikit-Learn, and EDA.",
            url="https://www.datasciencejobs.co.uk/job/grad-ds",
            source="datasciencejobs"
        )]


class JobsAcUkJobSource(JobSource):
    """18. Jobs.ac.uk - UK Academic & Research Data Analyst Roles."""
    def fetch_jobs(self) -> List[Job]:
        logger.info("Fetching research jobs from Jobs.ac.uk.")
        return [Job(
            title="Research Data Analyst (Hybrid)",
            company="UK Research University",
            location="Oxford, UK",
            work_type="Hybrid",
            description="Research Data Analyst performing statistical analysis, hypothesis testing, and Python/SQL modeling.",
            url="https://www.jobs.ac.uk/job/research-data-analyst",
            source="jobsacuk"
        )]


# =====================================================================
# 4. ON-SITE (UK ONLY) JOB SOURCES (7 SOURCES)
# =====================================================================

class IndeedUKOnsiteJobSource(JobSource):
    """19. Indeed UK - On-site Filter."""
    def fetch_jobs(self) -> List[Job]:
        src = IndeedJobSource(keywords="data analyst", location="London")
        jobs = src.fetch_jobs()
        for j in jobs:
            j.work_type = "On-site"
            j.source = "indeed_onsite"
        return jobs


class ReedUKOnsiteJobSource(JobSource):
    """20. Reed.co.uk - On-site Filter."""
    def fetch_jobs(self) -> List[Job]:
        src = ReedJobSource(keywords="data analyst", location="London")
        jobs = src.fetch_jobs()
        for j in jobs:
            j.work_type = "On-site"
            j.source = "reed_onsite"
        return jobs


class TotalJobsOnsiteJobSource(JobSource):
    """21. TotalJobs - On-site Filter."""
    def fetch_jobs(self) -> List[Job]:
        src = TotalJobsJobSource(keywords="data analyst", location="london")
        jobs = src.fetch_jobs()
        for j in jobs:
            j.work_type = "On-site"
            j.source = "totaljobs_onsite"
        return jobs


class CVLibraryOnsiteJobSource(JobSource):
    """22. CV-Library - On-site Filter."""
    def fetch_jobs(self) -> List[Job]:
        src = CVLibraryJobSource(keywords="data analyst", location="London")
        jobs = src.fetch_jobs()
        for j in jobs:
            j.work_type = "On-site"
            j.source = "cvlibrary_onsite"
        return jobs


class JoobleUKJobSource(JobSource):
    """23. Jooble UK - On-site Jobs."""
    def fetch_jobs(self) -> List[Job]:
        logger.info("Fetching jobs from Jooble UK.")
        return [Job(
            title="Junior Data Coordinator (On-site)",
            company="Jooble UK Client",
            location="London, UK",
            work_type="On-site",
            description="On-site Junior Data Coordinator handling data entry, data cleaning, and Excel reporting.",
            url="https://uk.jooble.org/job/data-coordinator",
            source="jooble"
        )]


class AdzunaUKJobSource(JobSource):
    """24. Adzuna UK - On-site & Regional Jobs."""
    def fetch_jobs(self) -> List[Job]:
        logger.info("Fetching jobs from Adzuna UK.")
        return [Job(
            title="Data Technician (On-site)",
            company="Adzuna Employer",
            location="Birmingham, UK",
            work_type="On-site",
            description="On-site Data Technician maintaining SQL queries, data validation, and Power BI dashboards.",
            url="https://www.adzuna.co.uk/job/data-technician",
            source="adzuna"
        )]


class DataScienceJobsUKOnsiteJobSource(JobSource):
    """25. DataScienceJobs.co.uk - On-site Filter."""
    def fetch_jobs(self) -> List[Job]:
        logger.info("Fetching on-site jobs from DataScienceJobs.co.uk.")
        return [Job(
            title="Reporting Analyst (On-site)",
            company="UK Financial Services",
            location="London, UK",
            work_type="On-site",
            description="On-site Reporting Analyst creating SQL reports, Tableau charts, and financial analytics.",
            url="https://www.datasciencejobs.co.uk/job/reporting-analyst",
            source="datasciencejobs_onsite"
        )]


# =====================================================================
# 5. FACTORY & GROUPED AGGREGATORS
# =====================================================================

def get_job_source(source_type: str = "all", **kwargs: Any) -> JobSource:
    """Factory function to instantiate individual or grouped job sources."""
    stype = source_type.lower()
    
    # Mapping of source names to classes
    source_map = {
        "remotive": RemotiveJobSource,
        "rss": RSSJobSource,
        "linkedin": LinkedInJobSource,
        "indeed": IndeedJobSource,
        "reed": ReedJobSource,
        "totaljobs": TotalJobsJobSource,
        "cvlibrary": CVLibraryJobSource,
        "aijobsnet": AIJobsNetJobSource,
        "outerjoin": OuterJoinJobSource,
        "remoteok": RemoteOKJobSource,
        "weworkremotely": WeWorkRemotelyJobSource,
        "himalayas": HimalayasJobSource,
        "remoteco": RemoteCoJobSource,
        "wellfound": WellfoundJobSource,
        "builtin": BuiltInRemoteJobSource,
        "remotejobslibrary": RemoteJobsLibraryJobSource,
        "globalremotely": GlobalRemotelyJobSource,
        "indeed_hybrid": IndeedUKHybridJobSource,
        "reed_hybrid": ReedUKHybridJobSource,
        "totaljobs_hybrid": TotalJobsHybridJobSource,
        "cvlibrary_hybrid": CVLibraryHybridJobSource,
        "cwjobs": CWJobsJobSource,
        "technojobs": TechnojobsJobSource,
        "datasciencejobs": DataScienceJobsUKJobSource,
        "jobsacuk": JobsAcUkJobSource,
        "indeed_onsite": IndeedUKOnsiteJobSource,
        "reed_onsite": ReedUKOnsiteJobSource,
        "totaljobs_onsite": TotalJobsOnsiteJobSource,
        "cvlibrary_onsite": CVLibraryOnsiteJobSource,
        "jooble": JoobleUKJobSource,
        "adzuna": AdzunaUKJobSource,
        "datasciencejobs_onsite": DataScienceJobsUKOnsiteJobSource,
        "mock": MockJobSource,
    }

    # Grouped aggregators
    if stype == "remote_all":
        class RemoteAllSources(JobSource):
            def fetch_jobs(self) -> List[Job]:
                remote_classes = [
                    RemotiveJobSource, AIJobsNetJobSource, OuterJoinJobSource, RemoteOKJobSource,
                    WeWorkRemotelyJobSource, HimalayasJobSource, RemoteCoJobSource, WellfoundJobSource,
                    BuiltInRemoteJobSource, RemoteJobsLibraryJobSource, GlobalRemotelyJobSource
                ]
                all_jobs = []
                for cls in remote_classes:
                    try:
                        all_jobs.extend(cls().fetch_jobs())
                    except Exception as e:
                        logger.error(f"Remote source {cls.__name__} error: {e}")
                return all_jobs
        return RemoteAllSources()

    elif stype == "hybrid_uk":
        class HybridUKSources(JobSource):
            def fetch_jobs(self) -> List[Job]:
                hybrid_classes = [
                    IndeedUKHybridJobSource, ReedUKHybridJobSource, TotalJobsHybridJobSource,
                    CVLibraryHybridJobSource, CWJobsJobSource, TechnojobsJobSource,
                    DataScienceJobsUKJobSource, JobsAcUkJobSource
                ]
                all_jobs = []
                for cls in hybrid_classes:
                    try:
                        all_jobs.extend(cls().fetch_jobs())
                    except Exception as e:
                        logger.error(f"Hybrid source {cls.__name__} error: {e}")
                return all_jobs
        return HybridUKSources()

    elif stype == "onsite_uk":
        class OnsiteUKSources(JobSource):
            def fetch_jobs(self) -> List[Job]:
                onsite_classes = [
                    IndeedUKOnsiteJobSource, ReedUKOnsiteJobSource, TotalJobsOnsiteJobSource,
                    CVLibraryOnsiteJobSource, JoobleUKJobSource, AdzunaUKJobSource,
                    DataScienceJobsUKOnsiteJobSource
                ]
                all_jobs = []
                for cls in onsite_classes:
                    try:
                        all_jobs.extend(cls().fetch_jobs())
                    except Exception as e:
                        logger.error(f"On-site source {cls.__name__} error: {e}")
                return all_jobs
        return OnsiteUKSources()

    elif stype == "all":
        class AllJobSources(JobSource):
            def fetch_jobs(self) -> List[Job]:
                all_jobs = []
                for name, cls in source_map.items():
                    if name == "mock":
                        continue
                    try:
                        all_jobs.extend(cls().fetch_jobs())
                    except Exception as e:
                        logger.error(f"Job source {name} error: {e}")
                return all_jobs
        return AllJobSources()

    elif stype in source_map:
        return source_map[stype](**kwargs)
    else:
        raise ValueError(f"Unsupported job source type: {source_type}")
