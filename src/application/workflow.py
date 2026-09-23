"""End-to-end workflow orchestrator for job search, evaluation, tailoring, and application logging."""

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
from src.notifications.email_notifier import EmailNotifier

logger = setup_logger("workflow")


class ApplicationWorkflow:
    """Orchestrates end-to-end job application flow with email notifications."""

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
        self.email_notifier = EmailNotifier(config_path=notifications_config_path, enabled=notify)

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
        5. Send notifications (application alerts, daily summary).
        6. Return list of structured output dictionaries matching required schema.
        """
        logger.info(f"Starting ApplicationWorkflow (source={source_name}, dry_run={dry_run})")
        
        # Step 1: Load profile & fetch jobs
        profile = self.profile_manager.load_profile()
        source = get_job_source(source_name)
        raw_jobs = source.fetch_jobs()

        if max_jobs and max_jobs > 0:
            raw_jobs = raw_jobs[:max_jobs]

        total_fetched = len(raw_jobs)
        total_skipped = 0
        total_rejected = 0
        applied_jobs_list = []

        # Step 2 & 3: Filter jobs & track rejections
        accepted_tuples = []
        for job in raw_jobs:
            is_valid, reason, skills = self.job_filter.evaluate_job(job)
            if is_valid:
                accepted_tuples.append((job, reason, skills))
            else:
                total_rejected += 1
                logger.info(f"[REJECT] {job.title} at {job.company} - {reason}")
                self.email_notifier.send_application_alert({
                    "title": job.title,
                    "company": job.company,
                    "location": job.location,
                    "url": job.url,
                    "reason": reason
                }, status="rejected")

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
                self.email_notifier.send_application_alert(job_dict, status="duplicate")
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
                
                # Send individual application notification
                self.email_notifier.send_application_alert(job_dict, status="applied")
                applied_jobs_list.append(job_dict)

                # Validate output schema against WorkflowJobResult Pydantic model
                validated_result = WorkflowJobResult(**output_item)
                results.append(validated_result.model_dump())

            except Exception as e:
                logger.error(f"Error processing job {job.title} at {job.company}: {e}", exc_info=True)
                self.email_notifier.send_error_alert(f"Error processing job {job.title} at {job.company}: {str(e)}")
                if not dry_run:
                    self.tracker.log_application(job, status="error", notes=f"Error: {str(e)}")

        logger.info(f"Workflow completed. Processed {len(results)} applications successfully.")

        # Step 6: Send daily summary email
        summary_dict = {
            "total_fetched": total_fetched,
            "total_applied": len(results),
            "total_skipped": total_skipped,
            "total_rejected": total_rejected,
            "applied_jobs": applied_jobs_list
        }
        self.email_notifier.send_daily_summary(summary_dict)

        return results
