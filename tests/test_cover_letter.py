"""Unit tests for cover letter generation logic in data/cover_letter.py."""

import pytest
from src.core.models import Profile, Job, ResumeVersion, CoverLetter
from src.data.cover_letter import CoverLetterGenerator


@pytest.fixture
def profile():
    return Profile(
        name="Shubham",
        contact={"email": "shubham@example.com"},
        skills=["Python", "SQL", "Power BI", "Tableau", "EDA", "Statistics"],
        projects=[{
            "title": "Maternal Health Risk Analysis",
            "tech_stack": ["Python", "SQL", "Scikit-Learn"],
            "description": "Predictive modeling and dashboard generation."
        }]
    )


@pytest.fixture
def job():
    return Job(
        title="Graduate Data Scientist",
        company="AI Insights Labs",
        location="Remote",
        work_type="Remote",
        description="Graduate Data Scientist position requiring Python, SQL, statistics, ML basics, and exploratory data analysis.",
        url="https://example.com/grad-ds"
    )


@pytest.fixture
def resume(job):
    return ResumeVersion(
        job_id=job.job_id,
        text="Resume text...",
        keywords=["Python", "SQL", "Statistics"],
        score=0.88
    )


def test_cover_letter_generator_deterministic(profile, job, resume):
    generator = CoverLetterGenerator(use_llm=False)
    cover_letter = generator.generate(profile, job, resume)

    assert isinstance(cover_letter, CoverLetter)
    assert cover_letter.job_id == job.job_id
    assert cover_letter.tone == "professional"

    text = cover_letter.text
    # Verify exact required references
    assert "Graduate Data Scientist" in text
    assert "AI Insights Labs" in text
    assert "learn" in text.lower() or "adapt" in text.lower() or "grow" in text.lower()

    # Word count check
    words_count = cover_letter.length_words
    assert 140 <= words_count <= 230, f"Word count {words_count} out of 150-220 range"
