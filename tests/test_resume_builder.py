"""Unit tests for ATS resume tailoring logic in data/resume_builder.py."""

import pytest
from src.core.models import Profile, Job, ResumeVersion
from src.data.resume_builder import ResumeBuilder
from src.data.profile_manager import ProfileManager


@pytest.fixture
def optimized_profile():
    return Profile(
        name="Shubham S. Shirodkar",
        profile_summary="Results-oriented Data Analyst and MSc Artificial Intelligence & Data Science candidate with published research.",
        contact={"email": "shirodkarshubham9@gmail.com", "phone": "+44 7721 708679", "location": "United Kingdom"},
        skills={
            "programming_languages": ["Python", "SQL"],
            "databases_and_sql": ["PostgreSQL", "MySQL"],
            "data_science_and_ml": ["Exploratory Data Analysis (EDA)", "Statistical Analysis", "XGBoost", "LightGBM", "Scikit-Learn"],
            "visualization_and_bi": ["Power BI", "Tableau"]
        },
        projects=[{
            "title": "Maternal Health Risk Prediction (Published Research)",
            "tech_stack": ["Python", "SQL", "Scikit-Learn", "XGBoost", "LightGBM", "Tableau"],
            "star_summary": {
                "situation": "Clinical risk prediction models suffer from class imbalance.",
                "task": "Develop ML classification pipeline.",
                "action": "Trained Voting Ensemble (XGBoost + LightGBM).",
                "result": "Achieved 0.889 macro recall score and built Tableau dashboard."
            }
        }],
        experience=[{
            "role": "Junior Data Analyst / Project Intern",
            "company": "Data Solutions Lab",
            "duration": "2023 - 2024",
            "highlights": ["Queried relational databases using SQL to extract actionable business metrics."]
        }],
        education=[{
            "degree": "MSc Artificial Intelligence & Data Science",
            "institution": "Solent University",
            "graduation_year": 2026
        }]
    )


@pytest.fixture
def target_job():
    return Job(
        title="Junior Data Analyst",
        company="UK Analytics Corp",
        location="London",
        work_type="Hybrid",
        description="Seeking a Junior Data Analyst proficient in Python, SQL, Excel, data cleaning, exploratory data analysis (EDA), and Power BI dashboards.",
        url="https://example.com/uk-data-analyst"
    )


def test_optimized_profile_loading():
    manager = ProfileManager("config/user_profile.yaml")
    profile = manager.load_profile()

    assert profile.name == "Shubham S. Shirodkar"
    assert profile.profile_summary is not None
    assert "MSc Artificial Intelligence" in profile.profile_summary
    assert len(profile.projects) >= 3


def test_resume_builder_ats_keyword_extraction(optimized_profile, target_job):
    builder = ResumeBuilder(use_llm=False)
    keywords, score = builder._calculate_ats_score(optimized_profile, target_job)

    assert score >= 0.70
    assert "Python" in keywords or "Sql" in keywords or "Power Bi" in keywords or "Eda" in keywords


def test_resume_builder_deterministic_generation(optimized_profile, target_job):
    builder = ResumeBuilder(use_llm=False)
    resume = builder.build_resume(optimized_profile, target_job)

    assert isinstance(resume, ResumeVersion)
    assert resume.score >= 0.70
    assert "Shubham S. Shirodkar" in resume.text
    assert "MSc Artificial Intelligence & Data Science" in resume.text
    assert "Maternal Health Risk Prediction" in resume.text
    assert "Programming Languages: Python, SQL" in resume.text or "Python" in resume.text
