"""Application tracker for logging applications, statuses, notes, and follow-ups."""

import os
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from src.core.models import ApplicationLog, Job
from src.core.utils import setup_logger

logger = setup_logger("tracker")


class ApplicationTracker:
    """Manages local JSON database for tracking application logs and preventing duplicate applications."""

    def __init__(self, db_path: str = "data/applications_tracker.json"):
        self.db_path = db_path
        self._logs: Dict[str, Dict[str, Any]] = {}
        self._load_logs()

    def _load_logs(self) -> None:
        """Load existing application logs from disk."""
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, "r", encoding="utf-8") as f:
                    self._logs = json.load(f)
                logger.info(f"Loaded {len(self._logs)} tracked applications from {self.db_path}")
            except Exception as e:
                logger.error(f"Error loading tracker file: {e}")
                self._logs = {}
        else:
            self._logs = {}

    def is_already_processed(self, job_id: str) -> bool:
        """Check if job has already been logged/processed."""
        return job_id in self._logs

    def log_application(
        self,
        job: Job,
        status: str = "prepared",
        notes: str = "",
        follow_up_days: int = 7
    ) -> ApplicationLog:
        """Log a new application entry or update existing status."""
        job_id = job.job_id or "job_default"
        now = datetime.now()
        follow_up_date = (now + timedelta(days=follow_up_days)).strftime("%Y-%m-%d")

        log_entry = ApplicationLog(
            job_id=job_id,
            status=status,
            submitted_at=now.isoformat(),
            notes=notes or f"Application for {job.title} at {job.company}",
            follow_up_date=follow_up_date
        )

        self._logs[job_id] = {
            **log_entry.model_dump(),
            "job_title": job.title,
            "company": job.company,
            "url": job.url
        }

        self._save_logs()
        logger.info(f"Logged application [{status.upper()}] for {job.title} at {job.company} (Follow-up: {follow_up_date})")
        return log_entry

    def get_log(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve log entry for a specific job_id."""
        return self._logs.get(job_id)

    def get_all_logs(self) -> List[Dict[str, Any]]:
        """Get list of all tracked application records."""
        return list(self._logs.values())

    def _save_logs(self) -> None:
        """Persist application logs to JSON file."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with open(self.db_path, "w", encoding="utf-8") as f:
            json.dump(self._logs, f, indent=2)
