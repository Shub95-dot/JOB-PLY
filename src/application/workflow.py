"""End-to-end workflow orchestrator for job search, evaluation, tailoring, and application logging."""

import os
from typing import List, Dict, Any, Optional
from src.core.models import Job, Profile, WorkflowJobResult
from src.core.utils import setup_logger
from src.data.profile_manager import ProfileManager
from src.data.resume_builder import ResumeBuilder
from src.data.cover_letter import CoverLetterGenerator
from src.jobs.job_sources import get_job_source
from src.jobs.job_filter import JobFilter
from src.application.form_filler import FormFiller
from src.application.tracker import ApplicationTracker
from src.notifications.discord_notifier import DiscordNotifier

logger = setup_logger("workflow")


class ApplicationWorkflow:
    """Orchestrates end-to-end job application flow with Discord webhook notifications."""

    def __init__(
        self,
        profile_path: str = "config/user_profile.yaml",
        filter_config_path: str = "config/filters.yaml",
        tracker_db_path: str = "data/applications_tracker.json",
        notifications_config_path: str = "config/notifications.yaml",
        use_llm: bool = True,
        notify: bool = True
    ):
        self.profile_manager = ProfileManager(profile_path)
        self.job_filter = JobFilter(filter_config_path)
        self.resume_builder = ResumeBuilder(use_llm=use_llm)
        self.cover_letter_gen = CoverLetterGenerator(use_llm=use_llm)
        self.form_filler = FormFiller()
        self.tracker = ApplicationTracker(tracker_db_path)
        self.discord_notifier = DiscordNotifier(config_path=notifications_config_path, enabled=notify)

    def _generate_interview_prep(self, job: Job, matched_skills: List[str], ats_score: float) -> Dict[str, Any]:
        """Generates interview prep guide markdown and stores in interview_prep/."""
        os.makedirs("interview_prep", exist_ok=True)
        safe_company = "".join(c for c in job.company if c.isalnum() or c in (" ", "_")).strip().replace(" ", "_")
        safe_title = "".join(c for c in job.title if c.isalnum() or c in (" ", "_")).strip().replace(" ", "_")
        filename = f"{safe_company}_{safe_title}.md"
        filepath = os.path.join("interview_prep", filename)

        tools = ["SQL", "Python", "Power BI", "Tableau", "Excel"]
        matched_tools = [t for t in tools if any(t.lower() in s.lower() for s in (matched_skills + job.description.split()))]
        if not matched_tools:
            matched_tools = ["SQL", "Python", "Power BI"]

        topics = ["SQL JOINs & Aggregations", "Data Cleaning Pipelines", "EDA & Statistical Metrics", "Predictive Modeling Basics"]

        prep_content = (
            f"# Technical Interview Preparation Guide\n\n"
            f"**Company**: {job.company}\n"
            f"**Role**: {job.title}\n"
            f"**Location**: {job.location} ({job.work_type})\n"
            f"**ATS Score**: {ats_score * 100:.0f}%\n\n"
            f"## Required Core Skills\n"
            f"{', '.join(matched_skills) if matched_skills else 'Python, SQL, EDA'}\n\n"
            f"## Required Tools\n"
            f"{', '.join(matched_tools)}\n\n"
            f"## Key Responsibilities\n"
            f"{job.description[:300]}...\n\n"
            f"## Topics To Revise\n"
            f"- " + "\n- ".join(topics) + "\n"
        )

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(prep_content)

        prep_data = {
            "company": job.company,
            "title": job.title,
            "required_skills": matched_skills or ["Python", "SQL", "EDA"],
            "required_tools": matched_tools,
            "key_responsibilities": (job.description[:250] + "...") if len(job.description) > 250 else job.description,
            "topics_to_revise": topics,
            "file_path": filepath
        }

        self.discord_notifier.send_interview_prep_alert(prep_data)
        return prep_data

    def run(
        self,
        source_name: str = "remotive",
        dry_run: bool = False,
        max_jobs: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Executes complete application workflow:
        1. Fetch raw jobs from source.
        2. Parse & normalize into Job models.
        3. Filter jobs via job_filter.
        4. For each accepted job: build ResumeVersion, CoverLetter, FormSubmissionPayload, track application.
        5. Send Discord notifications (application alerts, interview prep, daily summary).
        6. Return list of structured output dictionaries matching required schema.
        """
        logger.info(f"Starting ApplicationWorkflow (source={source_name}, dry_run={dry_run})")
        
        try:
            profile = self.profile_manager.load_profile()
            source = get_job_source(source_name)
            raw_jobs = source.fetch_jobs()
        except Exception as e:
            logger.error(f"Failed to fetch jobs from source {source_name}: {e}")
            self.discord_notifier.send_error_alert(f"Scraping/API failure fetching jobs from '{source_name}': {e}", category="Scraping/API Failure")
            return []

        if max_jobs and max_jobs > 0:
            raw_jobs = raw_jobs[:max_jobs]

        total_fetched = len(raw_jobs)
        total_skipped = 0
        total_rejected = 0
        senior_rejected = 0
        applied_jobs_list = []
        top_companies = []

        # Step 2 & 3: Filter jobs & track rejections
        accepted_tuples = []
        for job in raw_jobs:
            is_valid, reason, skills = self.job_filter.evaluate_job(job)
            if is_valid:
                accepted_tuples.append((job, reason, skills))
            else:
                total_rejected += 1
                if "senior" in reason.lower() or "5+ years" in reason.lower() or "experience" in reason.lower():
                    senior_rejected += 1
                logger.info(f"[REJECT] {job.title} at {job.company} - {reason}")
                self.discord_notifier.send_rejection_alert({
                    "title": job.title,
                    "company": job.company,
                    "location": job.location,
                    "url": job.url
                }, reason=reason)

        logger.info(f"Filtered {total_fetched} jobs -> {len(accepted_tuples)} accepted roles.")

        results = []
        for job, match_reason, matched_skills in accepted_tuples:
            job_id = job.job_id or "job_default"
            job_dict = {
                "title": job.title,
                "company": job.company,
                "location": job.location,
                "work_type": job.work_type,
                "url": job.url
            }

            # Check for duplicate
            if self.tracker.is_already_processed(job_id) and not dry_run:
                total_skipped += 1
                logger.info(f"Skipping already processed job {job.title} at {job.company}")
                self.discord_notifier.send_duplicate_alert(job_dict)
                continue

            try:
                # Step 4: Resume tailoring
                resume_ver = self.resume_builder.build_resume(profile, job)

                # Step 4: Cover letter generation
                cover_let = self.cover_letter_gen.generate(profile, job, resume_ver)

                # Step 4: Form filler mapping
                submission_payload = self.form_filler.build_submission_payload(profile, job, resume_ver, cover_let)

                # Step 4: Tracker logging
                status = "prepared" if dry_run else "submitted"
                if not dry_run:
                    self.tracker.log_application(job, status=status, notes="Auto-submitted via workflow")

                # Step 5: Format structured JSON output per job
                output_item = {
                    "job": job_dict,
                    "match_reason": match_reason,
                    "required_skills": matched_skills,
                    "resume_version": {
                        "text": resume_ver.text,
                        "keywords": resume_ver.keywords,
                        "score": resume_ver.score
                    },
                    "cover_letter": {
                        "text": cover_let.text,
                        "tone": cover_let.tone,
                        "length_words": cover_let.length_words
                    },
                    "application": {
                        "status": status,
                        "next_actions": "Review prepared application materials" if dry_run else "Track response and follow up in 7 days"
                    }
                }
                
                # Send individual application Discord alert
                self.discord_notifier.send_application_alert(
                    job_dict,
                    status="applied",
                    ats_score=resume_ver.score,
                    source_name=source_name
                )
                applied_jobs_list.append(job_dict)
                if job.company not in top_companies:
                    top_companies.append(job.company)

                # Generate interview prep guide & send alert
                self._generate_interview_prep(job, matched_skills, resume_ver.score)

                # Validate output schema against WorkflowJobResult Pydantic model
                validated_result = WorkflowJobResult(**output_item)
                results.append(validated_result.model_dump())

            except Exception as e:
                logger.error(f"Error processing job {job.title} at {job.company}: {e}", exc_info=True)
                self.discord_notifier.send_error_alert(
                    f"Error processing job '{job.title}' at '{job.company}': {str(e)}",
                    category="Workflow Exception"
                )
                if not dry_run:
                    self.tracker.log_application(job, status="error", notes=f"Error: {str(e)}")

        logger.info(f"Workflow completed. Processed {len(results)} applications successfully.")

        # Step 6: Send daily summary embed
        summary_dict = {
            "total_fetched": total_fetched,
            "total_applied": len(results),
            "total_skipped": total_skipped,
            "total_rejected": total_rejected,
            "senior_rejected": senior_rejected,
            "top_sources": [source_name],
            "top_companies": top_companies,
            "applied_jobs": applied_jobs_list
        }
        self.discord_notifier.send_daily_summary(summary_dict)

        return results
