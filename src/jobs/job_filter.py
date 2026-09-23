"""Deterministic and testable job filtering engine based on role title, fresher-friendly experience levels, skills, and work type."""

import os
import re
from typing import List, Tuple, Dict, Any
from src.core.models import Job
from src.core.utils import setup_logger, load_yaml, clean_text

logger = setup_logger("job_filter")


class JobFilter:
    """Evaluates and filters job postings deterministically for fresher-friendly Data Analytics/Science roles."""

    def __init__(self, filter_config_path: str = "config/filters.yaml"):
        self.filter_config_path = filter_config_path
        self._load_config()

    def _load_config(self) -> None:
        """Load filter configuration rules."""
        if os.path.exists(self.filter_config_path):
            config = load_yaml(self.filter_config_path)
        else:
            config = {}

        self.include_titles = [t.lower() for t in config.get("include_titles", [
            "data analyst", "junior data analyst", "graduate data analyst",
            "reporting analyst", "insights analyst", "bi analyst", "mi analyst",
            "analytics engineer", "data scientist", "junior data scientist",
            "graduate data scientist", "data technician", "data associate",
            "data coordinator", "data operations analyst", "business analyst", "junior analyst"
        ])]
        self.allowed_levels = [l.lower() for l in config.get("allowed_levels", [
            "entry-level", "entry level", "fresher", "junior", "graduate", "trainee",
            "associate", "intern", "training provided", "mentorship available",
            "no experience required", "experience preferred", "experience desirable",
            "experience beneficial", "some experience", "exposure to analytics",
            "0-1 year", "0-2 years", "1-2 years", "0 years", "1 year", "2 years"
        ])]
        self.preferred_skills = [s.lower() for s in config.get("preferred_skills", [
            "python", "sql", "excel", "power bi", "tableau", "statistics", "ml basics",
            "machine learning", "data cleaning", "eda", "exploratory data analysis"
        ])]
        self.allowed_work_types = [w.lower() for w in config.get("allowed_work_types", [
            "remote", "hybrid", "on-site", "unspecified"
        ])]
        self.exclude_keywords = [e.lower() for e in config.get("exclude_keywords", [
            "senior", "lead", "principal", "manager", "head of", "director", "architect", "staff", "vp"
        ])]
        self.experience_exclusions = [e.lower() for e in config.get("experience_exclusions", [
            "3+ years", "4+ years", "5+ years", "6+ years", "7+ years", "8+ years", "10+ years",
            "3 years of experience", "4 years of experience", "5 years of experience",
            "extensive experience required", "must have proven experience", "must have industry experience"
        ])]

    def evaluate_job(self, job: Job) -> Tuple[bool, str, List[str]]:
        """
        Evaluates a Job model against deterministic filtering rules.
        Returns:
            Tuple[is_accepted: bool, match_reason: str, matched_skills: List[str]]
        """
        title_lower = job.title.lower()
        desc_lower = (job.title + " " + job.description).lower()
        work_type_lower = job.work_type.lower()

        # Rule 1: Exclude Senior / Manager / Principal / Architect roles UNLESS explicitly junior/graduate prefixed
        is_junior_prefixed = any(lvl in title_lower for lvl in ["junior", "graduate", "trainee", "intern", "entry", "fresher"])
        for ex in self.exclude_keywords:
            if ex in title_lower and not is_junior_prefixed:
                return False, f"Excluded senior keyword '{ex}' found in job title.", []

        # Rule 2: Exclude significant experience requirements (3+ years, extensive experience) in description
        for exp_ex in self.experience_exclusions:
            if exp_ex in desc_lower and not is_junior_prefixed:
                return False, f"Excluded high experience requirement '{exp_ex}' found in job description.", []

        # Check regex pattern for 3+ to 15+ years experience
        high_exp_match = re.search(r'\b([3-9]|\d{2})\+?\s*(years?|yrs?)\b(?!\s*of\s*education)', desc_lower)
        if high_exp_match and not is_junior_prefixed:
            matched_exp = high_exp_match.group(0)
            return False, f"Excluded high experience requirement pattern '{matched_exp}' found in description.", []

        # Rule 3: Role Title Matching
        title_matched = any(t in title_lower for t in self.include_titles)
        if not title_matched:
            # Check if title contains core analytics keywords
            if not any(k in title_lower for k in ["data", "analytics", "analyst", "insights", "reporting", "bi"]):
                return False, f"Job title '{job.title}' does not match target Data Analytics/Data Science roles.", []

        # Rule 4: Work type check
        if work_type_lower not in self.allowed_work_types and "unspecified" not in self.allowed_work_types:
            return False, f"Work type '{job.work_type}' not in allowed work types.", []

        # Rule 5: Fresher-friendly level check
        has_fresher_phrase = any(lvl in desc_lower or lvl in title_lower for lvl in self.allowed_levels)
        
        # Rule 6: Skill extraction & check
        matched_skills = []
        for skill in self.preferred_skills:
            if re.search(r'\b' + re.escape(skill) + r'\b', desc_lower):
                matched_skills.append(skill.title())

        matched_skills = list(set(matched_skills))

        # Accept if title matches and no high-experience exclusions were triggered
        match_reason = (
            f"Matched fresher-friendly title pattern ({job.title}) with {len(matched_skills)} core data skills "
            f"({', '.join(matched_skills[:4]) if matched_skills else 'Data analytics'})."
        )
        return True, match_reason, matched_skills

    def filter_jobs(self, jobs: List[Job]) -> List[Tuple[Job, str, List[str]]]:
        """
        Filters a list of Job models.
        Returns list of Tuples (accepted_job, match_reason, matched_skills).
        """
        accepted = []
        for job in jobs:
            is_valid, reason, skills = self.evaluate_job(job)
            if is_valid:
                logger.info(f"[ACCEPT] {job.title} at {job.company} - {reason}")
                accepted.append((job, reason, skills))
            else:
                logger.info(f"[REJECT] {job.title} at {job.company} - {reason}")
        return accepted
