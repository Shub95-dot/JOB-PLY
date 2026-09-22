"""Deterministic and testable job filtering engine based on role title, level, skills, and work type."""

import os
import re
from typing import List, Tuple, Dict, Any
from src.core.models import Job
from src.core.utils import setup_logger, load_yaml, clean_text

logger = setup_logger("job_filter")


class JobFilter:
    """Evaluates and filters job postings deterministically."""

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
            "data analyst", "junior data analyst", "business analyst",
            "junior data scientist", "graduate data scientist", "analytics engineer",
            "reporting analyst", "insights analyst", "data science trainee", "junior analyst"
        ])]
        self.allowed_levels = [l.lower() for l in config.get("allowed_levels", [
            "entry-level", "entry level", "junior", "graduate", "trainee", "associate", "intern", "training", "mentorship"
        ])]
        self.preferred_skills = [s.lower() for s in config.get("preferred_skills", [
            "python", "sql", "excel", "power bi", "tableau", "statistics", "ml basics", "machine learning", "data cleaning", "eda", "exploratory data analysis"
        ])]
        self.allowed_work_types = [w.lower() for w in config.get("allowed_work_types", [
            "remote", "hybrid", "on-site", "unspecified"
        ])]
        self.exclude_keywords = [e.lower() for e in config.get("exclude_keywords", [
            "senior", "lead", "principal", "manager", "head of", "director", "architect", "staff", "vp"
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

        # Rule 1: Exclude Senior / Manager / Principal roles UNLESS explicitly junior/graduate prefixed
        is_junior_prefixed = any(lvl in title_lower for lvl in ["junior", "graduate", "trainee", "intern", "entry"])
        for ex in self.exclude_keywords:
            if ex in title_lower and not is_junior_prefixed:
                return False, f"Excluded senior keyword '{ex}' found in job title.", []

        # Rule 2: Title matching
        title_matched = any(t in title_lower for t in self.include_titles)
        if not title_matched:
            # Check if title has analyst/data science keywords
            if not any(k in title_lower for k in ["data", "analytics", "analyst", "insights", "reporting"]):
                return False, f"Job title '{job.title}' does not match target Data Analytics/Junior Data Science roles.", []

        # Rule 3: Level matching (entry-level, junior, graduate, trainee, mentorship)
        has_allowed_level = any(lvl in title_lower or lvl in desc_lower for lvl in self.allowed_levels)
        # Also allow if description clearly mentions junior/entry or training without explicit level in title
        if not has_allowed_level and not title_matched:
            return False, "Job does not specify junior, entry-level, graduate, or trainee experience requirements.", []

        # Rule 4: Work type check
        if work_type_lower not in self.allowed_work_types and "unspecified" not in self.allowed_work_types:
            return False, f"Work type '{job.work_type}' not in allowed work types.", []

        # Rule 5: Skill extraction & check
        matched_skills = []
        for skill in self.preferred_skills:
            if re.search(r'\b' + re.escape(skill) + r'\b', desc_lower):
                matched_skills.append(skill.title())

        # Clean duplicate skill representations
        matched_skills = list(set(matched_skills))

        match_reason = (
            f"Matched title pattern and junior level criteria with {len(matched_skills)} core data skills "
            f"({', '.join(matched_skills[:4]) if matched_skills else 'General data analytics'})."
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
