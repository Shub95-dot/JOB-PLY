"""Unit tests for Pydantic domain models in core/models.py."""

import pytest
from src.core.models import (
    Job,
    Profile,
    ResumeVersion,
    CoverLetter,
    ApplicationLog,
    WorkflowJobResult
)


def test_job_model_id_generation():
    job = Job(
        title="Data Analyst",
        company="Acme Analytics",
        location="Remote",
        work_type="Remote",
        description="SQL, Python, Excel analysis.",
        url="https://acme.com/jobs/123",
        source="mock"
    )
    assert job.job_id is not None
    assert len(job.job_id) == 12
    assert job.title == "Data Analyst"


def test_profile_model():
    profile = Profile(
        name="Shubham",
        skills=["Python", "SQL", "Tableau"],
        projects=[{"title": "Maternal Health Analysis"}]
    )
    assert profile.name == "Shubham"
    assert "Python" in profile.skills
    assert len(profile.projects) == 1


def test_resume_version_score_validation():
    resume = ResumeVersion(
        job_id="job123",
        text="Resume content...",
        keywords=["Python", "SQL"],
        score=0.85
    )
    assert resume.score == 0.85

    with pytest.raises(ValueError):
        ResumeVersion(
            job_id="job123",
            text="Resume content...",
            keywords=[],
            score=1.5  # Invalid score > 1.0
        )


def test_cover_letter_model():
    cl = CoverLetter(
        job_id="job123",
        text="Dear Hiring Manager...",
        tone="professional",
        length_words=175
    )
    assert cl.length_words == 175
    assert cl.tone == "professional"


def test_application_log_model():
    log = ApplicationLog(
        job_id="job123",
        status="prepared",
        notes="Dry run test"
    )
    assert log.status == "prepared"
    assert log.submitted_at is not None


def test_workflow_job_result_schema():
    result = WorkflowJobResult(
        job={
            "title": "Junior Data Analyst",
            "company": "TechMetrics",
            "location": "London",
            "work_type": "Hybrid",
            "url": "https://example.com"
        },
        match_reason="Matches junior analyst title",
        required_skills=["Python", "SQL"],
        resume_version={
            "text": "Tailored resume",
            "keywords": ["Python", "SQL"],
            "score": 0.8
        },
        cover_letter={
            "text": "Dear team...",
            "tone": "professional",
            "length_words": 180
        },
        application={
            "status": "prepared",
            "next_actions": "Review material"
        }
    )
    assert result.job["title"] == "Junior Data Analyst"
    assert result.resume_version["score"] == 0.8
