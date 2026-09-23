"""Unit tests for UK and international job sources in src/jobs/job_sources.py."""

import pytest
from src.core.models import Job
from src.jobs.job_sources import (
    LinkedInJobSource,
    IndeedJobSource,
    ReedJobSource,
    TotalJobsJobSource,
    CVLibraryJobSource,
    RemotiveJobSource,
    RSSJobSource,
    MockJobSource,
    get_job_source,
)


def test_mock_job_source():
    source = MockJobSource()
    jobs = source.fetch_jobs()
    assert isinstance(jobs, list)
    assert len(jobs) > 0
    assert isinstance(jobs[0], Job)
    assert jobs[0].company == "TechMetrics Ltd"


def test_linkedin_job_source_structure():
    source = LinkedInJobSource(keywords="data analyst", location="United Kingdom", max_pages=1)
    jobs = source.fetch_jobs()
    assert isinstance(jobs, list)
    for job in jobs:
        assert isinstance(job, Job)
        assert job.source == "linkedin"
        assert job.url is not None


def test_indeed_job_source_structure():
    source = IndeedJobSource(keywords="data analyst", location="United Kingdom", max_pages=1)
    jobs = source.fetch_jobs()
    assert isinstance(jobs, list)
    for job in jobs:
        assert isinstance(job, Job)
        assert job.source == "indeed"


def test_reed_job_source_structure():
    source = ReedJobSource(keywords="data analyst", location="United Kingdom", max_pages=1)
    jobs = source.fetch_jobs()
    assert isinstance(jobs, list)
    for job in jobs:
        assert isinstance(job, Job)
        assert job.source == "reed"


def test_totaljobs_job_source_structure():
    source = TotalJobsJobSource(keywords="data analyst", location="united-kingdom", max_pages=1)
    jobs = source.fetch_jobs()
    assert isinstance(jobs, list)
    for job in jobs:
        assert isinstance(job, Job)
        assert job.source == "totaljobs"


def test_cvlibrary_job_source_structure():
    source = CVLibraryJobSource(keywords="data analyst", location="United Kingdom", max_pages=1)
    jobs = source.fetch_jobs()
    assert isinstance(jobs, list)
    for job in jobs:
        assert isinstance(job, Job)
        assert job.source == "cvlibrary"


@pytest.mark.parametrize("source_name", [
    "linkedin", "indeed", "reed", "totaljobs", "cvlibrary", "remotive", "rss", "mock"
])
def test_get_job_source_factory(source_name):
    source = get_job_source(source_name)
    assert source is not None
    assert hasattr(source, "fetch_jobs")


def test_get_job_source_all():
    multi_source = get_job_source("all")
    assert hasattr(multi_source, "fetch_jobs")
