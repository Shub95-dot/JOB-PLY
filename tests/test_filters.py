"""Unit tests for deterministic job filtering engine in jobs/job_filter.py."""

import pytest
from src.core.models import Job
from src.jobs.job_filter import JobFilter


@pytest.fixture
def job_filter():
    return JobFilter()


def test_accept_junior_data_analyst(job_filter):
    job = Job(
        title="Junior Data Analyst",
        company="Data Corp",
        location="Remote",
        work_type="Remote",
        description="Looking for Junior Data Analyst with Python, SQL, Excel, and Power BI skills.",
        url="https://example.com/job1"
    )
    is_valid, reason, skills = job_filter.evaluate_job(job)
    assert is_valid is True
    assert "Python" in skills or "python" in [s.lower() for s in skills]
    assert "SQL" in skills or "sql" in [s.lower() for s in skills]


def test_accept_graduate_data_scientist(job_filter):
    job = Job(
        title="Graduate Data Scientist",
        company="AI Research",
        location="London",
        work_type="Hybrid",
        description="Graduate training position. Requirements: Python, statistics, ML basics, data cleaning.",
        url="https://example.com/job2"
    )
    is_valid, reason, skills = job_filter.evaluate_job(job)
    assert is_valid is True


def test_reject_senior_manager_role(job_filter):
    job = Job(
        title="Senior Data Analytics Manager",
        company="Big Tech Inc",
        location="London",
        work_type="On-site",
        description="Lead a team of 20 analysts.",
        url="https://example.com/job3"
    )
    is_valid, reason, skills = job_filter.evaluate_job(job)
    assert is_valid is False
    assert "senior" in reason.lower() or "excluded" in reason.lower()


def test_reject_unrelated_role(job_filter):
    job = Job(
        title="Software Quality Assurance Tester",
        company="Software Co",
        location="Remote",
        work_type="Remote",
        description="Manual testing and Selenium scripts.",
        url="https://example.com/job4"
    )
    is_valid, reason, skills = job_filter.evaluate_job(job)
    assert is_valid is False


def test_batch_filter_jobs(job_filter):
    jobs = [
        Job(title="Junior Data Analyst", company="A", location="Remote", work_type="Remote", description="Python SQL", url="u1"),
        Job(title="Principal Architect", company="B", location="Remote", work_type="Remote", description="Senior lead", url="u2"),
    ]
    results = job_filter.filter_jobs(jobs)
    assert len(results) == 1
    assert results[0][0].title == "Junior Data Analyst"
