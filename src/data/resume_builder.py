"""ATS Resume tailoring logic for matching candidate profile against job descriptions."""

import os
import re
from typing import List, Tuple, Dict, Any, Union
from src.core.models import Profile, Job, ResumeVersion
from src.core.utils import setup_logger

logger = setup_logger("resume_builder")

CORE_DATA_KEYWORDS = [
    "python", "sql", "excel", "power bi", "tableau",
    "statistics", "ml basics", "machine learning", "data cleaning",
    "eda", "exploratory data analysis", "pandas", "numpy", "scikit-learn",
    "xgboost", "lightgbm", "fastapi", "streamlit", "hypothesis testing"
]


class ResumeBuilder:
    """Tailors candidate resume based on target job description requirements."""

    def __init__(self, use_llm: bool = True):
        self.use_llm = use_llm
        self.api_key = os.environ.get("ANTHROPIC_API_KEY")

    def build_resume(self, profile: Profile, job: Job) -> ResumeVersion:
        """
        Accepts Profile and Job domain models.
        Returns tailored ResumeVersion model with ATS score (0.0 to 1.0).
        """
        matched_keywords, score = self._calculate_ats_score(profile, job)
        
        if self.use_llm and self.api_key:
            resume_text = self._build_resume_llm(profile, job, matched_keywords)
        else:
            resume_text = self._build_resume_deterministic(profile, job, matched_keywords)

        return ResumeVersion(
            job_id=job.job_id or "job_default",
            text=resume_text,
            keywords=matched_keywords,
            score=round(score, 2)
        )

    def _extract_all_skills(self, profile: Profile) -> List[str]:
        """Extract flat list of skill strings regardless of whether skills is list or dict."""
        if isinstance(profile.skills, list):
            return profile.skills
        elif isinstance(profile.skills, dict):
            flat_skills = []
            for cat, skill_list in profile.skills.items():
                if isinstance(skill_list, list):
                    flat_skills.extend(skill_list)
            return flat_skills
        return []

    def _calculate_ats_score(self, profile: Profile, job: Job) -> Tuple[List[str], float]:
        """Extract JD keywords and compute ATS match score (0.0 to 1.0)."""
        jd_text = (job.title + " " + job.description).lower()
        all_skills = self._extract_all_skills(profile)
        candidate_skills = [s.lower() for s in all_skills]
        
        matched = []
        for kw in CORE_DATA_KEYWORDS:
            if kw in jd_text and (kw in candidate_skills or any(kw in str(p).lower() for p in profile.projects)):
                matched.append(kw.title())

        for skill in all_skills:
            skill_lower = skill.lower()
            if skill_lower in jd_text and skill.title() not in matched:
                matched.append(skill.title())

        found_count = len(matched)
        if not matched:
            score = 0.2
        else:
            score = min(1.0, 0.45 + (found_count * 0.07))

        return list(set(matched)), score

    def _build_resume_deterministic(self, profile: Profile, job: Job, keywords: List[str]) -> str:
        """Generate ATS-optimized resume text deterministically with STAR-style impact statements."""
        all_skills = self._extract_all_skills(profile)
        lines = []
        lines.append(f"NAME: {profile.name}")
        lines.append(f"CONTACT: {profile.contact.get('email', '')} | {profile.contact.get('phone', '')} | {profile.contact.get('location', '')}")
        lines.append(f"LINKEDIN: {profile.contact.get('linkedin', '')} | GITHUB: {profile.contact.get('github', '')}")
        lines.append("\n" + "="*40)
        lines.append("PROFESSIONAL SUMMARY")
        lines.append("="*40)
        
        summary = profile.profile_summary or (
            f"Results-driven Data Analytics & Junior Data Science professional with a strong background in "
            f"Applied AI, Python, SQL, data cleaning, exploratory data analysis (EDA), interactive dashboards, "
            f"and statistics. Tailored for the {job.title} position at {job.company}."
        )
        lines.append(summary)

        lines.append("\n" + "="*40)
        lines.append("CORE SKILLS & TECHNOLOGIES")
        lines.append("="*40)

        if isinstance(profile.skills, dict):
            for category, skill_list in profile.skills.items():
                cat_title = category.replace("_", " ").title()
                lines.append(f" • {cat_title}: {', '.join(skill_list)}")
        else:
            prioritized = sorted(all_skills, key=lambda s: s.title() not in keywords)
            lines.append(" • " + ", ".join(prioritized))

        lines.append("\n" + "="*40)
        lines.append("KEY PROJECTS & MEASURABLE ACHIEVEMENTS")
        lines.append("="*40)
        for proj in profile.projects:
            title = proj.get("title", "Project")
            tech = ", ".join(proj.get("tech_stack", []))
            lines.append(f"• {title} ({tech})")
            if "star_summary" in proj and isinstance(proj["star_summary"], dict):
                star = proj["star_summary"]
                lines.append(f"  - Action & Result: {star.get('action', '')} {star.get('result', '')}")
            elif "description" in proj:
                lines.append(f"  - {proj['description']}")

        lines.append("\n" + "="*40)
        lines.append("EXPERIENCE")
        lines.append("="*40)
        for exp in profile.experience:
            lines.append(f"• {exp.get('role', '')} - {exp.get('company', '')} ({exp.get('duration', '')})")
            for h in exp.get("highlights", []):
                lines.append(f"  - {h}")

        lines.append("\n" + "="*40)
        lines.append("EDUCATION")
        lines.append("="*40)
        for edu in profile.education:
            lines.append(f"• {edu.get('degree', '')}, {edu.get('institution', '')} ({edu.get('graduation_year', '')})")
            if "details" in edu:
                lines.append(f"  {edu['details']}")

        if profile.certifications:
            lines.append("\n" + "="*40)
            lines.append("CERTIFICATIONS")
            lines.append("="*40)
            for cert in profile.certifications:
                lines.append(f"• {cert.get('title', '')} - {cert.get('issuer', '')} ({cert.get('year', '')})")

        return "\n".join(lines)

    def _build_resume_llm(self, profile: Profile, job: Job, keywords: List[str]) -> str:
        """Calls Anthropic Claude API to generate ATS-tailored resume text."""
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self.api_key)

            prompt = f"""
You are an expert ATS Resume Coach for UK Data Analytics and Junior Data Science roles. Reorder and emphasize candidate background for target role:
Role: {job.title} at {job.company}
JD Excerpt: {job.description[:1000]}

Candidate Profile:
Name: {profile.name}
Summary: {profile.profile_summary}
Categorized Skills: {profile.skills}
Matched Keywords: {', '.join(keywords)}
STAR Projects & Achievements: {profile.projects}
Experience: {profile.experience}
Education: {profile.education}
Certifications: {profile.certifications}

Instructions:
- Emphasize Python, SQL, Power BI, Tableau, data cleaning, EDA, dashboards, ML algorithms (XGBoost, LightGBM, Scikit-Learn), statistics, and STAR achievements (macro recall scores, 40% speedup).
- Use ATS-friendly formatting.
- Never fabricate experience; only rephrase and reorder candidate details.
Return full formatted resume text.
"""
            response = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text.strip()
        except Exception as e:
            logger.warning(f"LLM resume building failed ({e}). Falling back to deterministic builder.")
            return self._build_resume_deterministic(profile, job, keywords)
