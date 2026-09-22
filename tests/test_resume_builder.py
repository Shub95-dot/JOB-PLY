"""Unit tests for ATS resume tailoring logic in data/resume_builder.py."""

import pytest
from src.core.models import Profile, Job, ResumeVersion
from src.data.resume_builder import ResumeBuilder


@pytest.fixture
def profile():
    return Profile(
        name="Shubham",
        contact={"email": "shubham@example.com", "phone": "+44123456789", "location": "UK"},
        skills=["Python", "SQL", "Excel", "Power BI", "Tableau", "EDA", "Statistics"],
        projects=[{
            "title": "Maternal Health Analysis",
            "tech_stack": ["Python", "SQL", "Power BI"],
            "description": "Exploratory data analysis and predictive modeling on healthcare datasets."
        }],
        experience=[{
            "role": "Junior Data Analyst",
            "company": "Data Lab",
            "duration": "2023 - 2024",
            "highlights": ["Built SQL queries and Power BI dashboards."]
        }],
        education=[{
            "degree": "B.Sc. Data Science",
            "institution": "University",
            "graduation_year": 2024
        }]
    )


@pytest.fixture
def job():
    return Job(
        title="Junior Data Analyst",
        company="TechMetrics",
        location="London",
        work_type="Hybrid",
        description="Looking for a Junior Data Analyst proficient in Python, SQL, Excel, data cleaning, and Power BI dashboards.",
        url="https://example.com/job1"
    )


def test_resume_builder_deterministic(profile, job):
    builder = ResumeBuilder(use_llm=False)
    resume = builder.build_resume(profile, job)

    assert isinstance(resume, ResumeVersion)
    assert resume.job_id == job.job_id
    assert 0.0 <= resume.score <= 1.0
    assert len(resume.keywords) > 0
    assert "Shubham" in resume.text
    assert "TechMetrics" in resume.text
    assert "Python" in resume.text or "SQL" in resume.text


def test_resume_builder_ats_score(profile, job):
    builder = ResumeBuilder(use_llm=False)
    keywords, score = builder._calculate_ats_score(profile, job)

    assert score >= 0.5
    assert "Python" in keywords or "Sql" in keywords or "Excel" in keywords
