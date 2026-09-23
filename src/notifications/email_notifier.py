"""Email notification service using Gmail SMTP."""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, Any, Optional, List
from src.core.utils import setup_logger, load_yaml

logger = setup_logger("email_notifier")


class EmailNotifier:
    """Handles sending email alerts, daily summaries, weekly summaries, and error reports via SMTP."""

    def __init__(self, config_path: str = "config/notifications.yaml", enabled: bool = True):
        self.enabled = enabled
        self.config_path = config_path
        self.provider = "gmail"
        self.smtp_host = "smtp.gmail.com"
        self.smtp_port = 587
        self.username = ""
        self.password = ""
        self.recipient_email = ""
        self.enable_application_alerts = True
        self.enable_daily_summary = True
        self.enable_weekly_summary = True

        self._load_config()

    def _load_config(self) -> None:
        if not os.path.exists(self.config_path):
            logger.warning(f"Notification config file not found at {self.config_path}. Email notifier disabled.")
            return

        try:
            config = load_yaml(self.config_path)
            self.provider = config.get("provider", "gmail")
            self.smtp_host = config.get("smtp_host", "smtp.gmail.com")
            self.smtp_port = int(config.get("smtp_port", 587))
            self.username = config.get("username", "")
            self.password = config.get("password", "")
            self.recipient_email = config.get("recipient_email", self.username)

            self.enable_application_alerts = config.get("enable_application_alerts", True)
            self.enable_daily_summary = config.get("enable_daily_summary", True)
            self.enable_weekly_summary = config.get("enable_weekly_summary", True)

            logger.info(f"EmailNotifier configured for {self.username} -> {self.recipient_email}")
        except Exception as e:
            logger.error(f"Error loading notification config: {e}")

    def send_email(self, subject: str, body: str, html_body: Optional[str] = None) -> bool:
        """Send an email using SMTP TLS authentication."""
        if not self.enabled:
            logger.debug(f"[DISABLED] Would send email: {subject}")
            return False

        if not self.username or not self.password or not self.recipient_email:
            logger.warning("SMTP credentials or recipient email missing. Email not sent.")
            return False

        try:
            msg = MIMEMultipart("alternative")
            msg["From"] = f"JOB-PLY Agent <{self.username}>"
            msg["To"] = self.recipient_email
            msg["Subject"] = subject

            msg.attach(MIMEText(body, "plain", "utf-8"))
            if html_body:
                msg.attach(MIMEText(html_body, "html", "utf-8"))

            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.send_message(msg)

            logger.info(f"Email sent successfully: '{subject}' to {self.recipient_email}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email '{subject}': {e}")
            return False

    def send_application_alert(self, job_data: Dict[str, Any], status: str = "applied") -> bool:
        """Send an alert for individual job events (applied, duplicate, rejected)."""
        if not self.enable_application_alerts:
            return False

        title = job_data.get("title", "Unknown Title")
        company = job_data.get("company", "Unknown Company")
        location = job_data.get("location", "Unknown Location")
        url = job_data.get("url", "#")
        work_type = job_data.get("work_type", "N/A")

        if status == "applied":
            subject = f"🎯 [JOB-PLY] Applied: {title} at {company}"
            body = (
                f"Job Application Submitted & Materials Prepared!\n\n"
                f"• Title: {title}\n"
                f"• Company: {company}\n"
                f"• Location: {location} ({work_type})\n"
                f"• URL: {url}\n\n"
                f"Generated tailored resume and recruiter-optimized cover letter for Shubham S. Shirodkar.\n"
            )
        elif status == "duplicate":
            subject = f"⏭️ [JOB-PLY] Skipped Duplicate: {title} at {company}"
            body = (
                f"Skipped duplicate job application.\n\n"
                f"• Title: {title}\n"
                f"• Company: {company}\n"
                f"• URL: {url}\n"
            )
        elif status == "rejected":
            reason = job_data.get("reason", "Senior or 3+ years experience requirement")
            subject = f"🛡️ [JOB-PLY] Filtered Out: {title} at {company}"
            body = (
                f"Job posting filtered out (Fresher-friendly rule enforcement).\n\n"
                f"• Title: {title}\n"
                f"• Company: {company}\n"
                f"• Reason: {reason}\n"
                f"• URL: {url}\n"
            )
        else:
            subject = f"ℹ️ [JOB-PLY] Update: {title} at {company}"
            body = f"Job Event ({status}): {title} at {company}\nURL: {url}\n"

        return self.send_email(subject, body)

    def send_daily_summary(self, summary_dict: Dict[str, Any]) -> bool:
        """Send a daily execution summary email."""
        if not self.enable_daily_summary:
            return False

        total_fetched = summary_dict.get("total_fetched", 0)
        total_applied = summary_dict.get("total_applied", 0)
        total_skipped = summary_dict.get("total_skipped", 0)
        total_rejected = summary_dict.get("total_rejected", 0)
        applied_jobs: List[Dict[str, str]] = summary_dict.get("applied_jobs", [])

        subject = f"📊 [JOB-PLY Daily Report] Applied: {total_applied} | Fetched: {total_fetched}"

        applied_lines = ""
        if applied_jobs:
            for idx, item in enumerate(applied_jobs, 1):
                t = item.get("title", "Job")
                c = item.get("company", "Company")
                l = item.get("location", "")
                applied_lines += f"  {idx}. {t} @ {c} ({l})\n"
        else:
            applied_lines = "  (No new applications submitted today)\n"

        body = (
            f"Job-App-Agent Daily Execution Report\n"
            f"====================================\n\n"
            f"• Total Jobs Fetched: {total_fetched}\n"
            f"• Total Applied / Prepared: {total_applied}\n"
            f"• Total Skipped (Duplicates): {total_skipped}\n"
            f"• Total Filtered Out (Senior / 3+ Yrs): {total_rejected}\n\n"
            f"Applied Roles Today:\n"
            f"{applied_lines}\n"
            f"System status: Operational\n"
        )

        return self.send_email(subject, body)

    def send_weekly_summary(self, summary_dict: Dict[str, Any]) -> bool:
        """Send a weekly performance summary email."""
        if not self.enable_weekly_summary:
            return False

        total_weekly_apps = summary_dict.get("total_applications", 0)
        top_sources = summary_dict.get("top_sources", [])
        avg_ats_score = summary_dict.get("avg_ats_score", 0.0)
        interviews_received = summary_dict.get("interviews_received", 0)

        subject = f"📈 [JOB-PLY Weekly Report] {total_weekly_apps} Applications | ATS Avg: {avg_ats_score:.2f}"

        sources_str = ", ".join(top_sources) if top_sources else "N/A"

        body = (
            f"Job-App-Agent Weekly Summary Report\n"
            f"===================================\n\n"
            f"• Total Applications This Week: {total_weekly_apps}\n"
            f"• Top Job Sources: {sources_str}\n"
            f"• Average ATS Match Score: {avg_ats_score:.2f}\n"
            f"• Interviews Received: {interviews_received}\n\n"
            f"Keep up the momentum!\n"
        )

        return self.send_email(subject, body)

    def send_error_alert(self, error_message: str) -> bool:
        """Send an urgent error alert email."""
        subject = "🚨 [JOB-PLY ERROR ALERT] System Exception Encountered"
        body = (
            f"An error occurred during the job-app-agent workflow execution:\n\n"
            f"{error_message}\n\n"
            f"Please check logs/errors.log for complete traceback."
        )
        return self.send_email(subject, body)
