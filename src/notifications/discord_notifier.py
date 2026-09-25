"""Discord webhook notification service for JOB-PLY."""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
import requests
from src.core.utils import setup_logger, load_yaml

logger = setup_logger("discord_notifier")


class DiscordNotifier:
    """Handles sending Discord webhook alerts, embeds, summaries, interview prep, and error notifications."""

    def __init__(self, config_path: str = "config/notifications.yaml", enabled: bool = True):
        self.enabled = enabled
        self.config_path = config_path
        self.webhook_url = os.environ.get("DISCORD_APPLICATIONS_WEBHOOK", "").strip()

        self.enable_application_alerts = True
        self.enable_duplicate_alerts = True
        self.enable_rejection_alerts = True
        self.enable_daily_summary = True
        self.enable_weekly_summary = True
        self.enable_interview_prep_alerts = True
        self.enable_error_alerts = True

        self._load_config()

    def _load_config(self) -> None:
        """Loads notification configuration flags and validates webhook URL."""
        if os.path.exists(self.config_path):
            try:
                config = load_yaml(self.config_path)
                self.enable_application_alerts = config.get("enable_application_alerts", True)
                self.enable_duplicate_alerts = config.get("enable_duplicate_alerts", True)
                self.enable_rejection_alerts = config.get("enable_rejection_alerts", True)
                self.enable_daily_summary = config.get("enable_daily_summary", True)
                self.enable_weekly_summary = config.get("enable_weekly_summary", True)
                self.enable_interview_prep_alerts = config.get("enable_interview_prep_alerts", True)
                self.enable_error_alerts = config.get("enable_error_alerts", True)
            except Exception as e:
                logger.error(f"Error loading notification config: {e}")

        if not self.webhook_url:
            logger.warning("DISCORD_APPLICATIONS_WEBHOOK environment variable not set. Discord notifications disabled.")
            self.enabled = False
        else:
            logger.info("DiscordNotifier configured with valid webhook URL.")

    def send_webhook(self, payload: Dict[str, Any]) -> bool:
        """Send JSON payload to configured Discord webhook."""
        if not self.enabled or not self.webhook_url:
            logger.debug("DiscordNotifier disabled or missing webhook URL. Skipping webhook delivery.")
            return False

        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            if response.status_code in [200, 204]:
                logger.info("Discord webhook sent successfully.")
                return True
            else:
                logger.error(f"Failed to send Discord webhook: HTTP {response.status_code} - {response.text}")
                return False
        except Exception as e:
            logger.error(f"Error sending Discord webhook: {e}")
            return False

    def send_application_alert(
        self,
        job_data: Dict[str, Any],
        status: str = "applied",
        ats_score: float = 0.85,
        source_name: str = "Remotive"
    ) -> bool:
        """Send Discord embed when a job application is submitted."""
        if not self.enable_application_alerts:
            return False

        title = job_data.get("title", "Unknown Title")
        company = job_data.get("company", "Unknown Company")
        location = job_data.get("location", "Unknown Location")
        work_type = job_data.get("work_type", "N/A")
        url = job_data.get("url", "#")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        ats_str = f"{ats_score * 100:.0f}%" if isinstance(ats_score, float) and ats_score <= 1.0 else str(ats_score)

        embed = {
            "title": "✅ Application Submitted",
            "description": f"Successfully prepared & logged application materials for **{title}**!",
            "color": 0x2ECC71,  # Green
            "fields": [
                {"name": "🏢 Company", "value": company, "inline": True},
                {"name": "💼 Job Title", "value": title, "inline": True},
                {"name": "📍 Location", "value": f"{location} ({work_type})", "inline": True},
                {"name": "🎯 ATS Score", "value": ats_str, "inline": True},
                {"name": "📡 Job Source", "value": source_name, "inline": True},
                {"name": "⏰ Application Timestamp", "value": timestamp, "inline": True},
                {"name": "🔗 Job URL", "value": f"[View Job Posting]({url})", "inline": False}
            ],
            "footer": {"text": "JOB-PLY Automated Job Application Agent"}
        }

        return self.send_webhook({"embeds": [embed]})

    def send_duplicate_alert(self, job_data: Dict[str, Any]) -> bool:
        """Send alert for skipped duplicate jobs."""
        if not self.enable_duplicate_alerts:
            return False

        title = job_data.get("title", "Unknown Title")
        company = job_data.get("company", "Unknown Company")
        url = job_data.get("url", "#")

        embed = {
            "title": "⏭️ Skipped Duplicate Application",
            "description": f"Application to **{title}** at **{company}** was already processed.",
            "color": 0xF1C40F,  # Yellow
            "fields": [
                {"name": "Company", "value": company, "inline": True},
                {"name": "Job Title", "value": title, "inline": True},
                {"name": "URL", "value": url, "inline": False}
            ],
            "footer": {"text": "JOB-PLY Tracker Guard"}
        }

        return self.send_webhook({"embeds": [embed]})

    def send_rejection_alert(self, job_data: Dict[str, Any], reason: str = "Senior requirement") -> bool:
        """Send alert for filtered out jobs."""
        if not self.enable_rejection_alerts:
            return False

        title = job_data.get("title", "Unknown Title")
        company = job_data.get("company", "Unknown Company")
        url = job_data.get("url", "#")

        embed = {
            "title": "🛡️ Job Filtered Out",
            "description": f"Job **{title}** at **{company}** was excluded by criteria filters.",
            "color": 0xE74C3C,  # Red
            "fields": [
                {"name": "Company", "value": company, "inline": True},
                {"name": "Job Title", "value": title, "inline": True},
                {"name": "Filter Reason", "value": reason, "inline": False},
                {"name": "URL", "value": url, "inline": False}
            ],
            "footer": {"text": "JOB-PLY Fresher-Friendly Filter Engine"}
        }

        return self.send_webhook({"embeds": [embed]})

    def send_daily_summary(self, summary_dict: Dict[str, Any]) -> bool:
        """Send daily execution summary embed."""
        if not self.enable_daily_summary:
            return False

        total_fetched = summary_dict.get("total_fetched", 0)
        total_applied = summary_dict.get("total_applied", 0)
        total_skipped = summary_dict.get("total_skipped", 0)
        total_rejected = summary_dict.get("total_rejected", 0)
        senior_rejected = summary_dict.get("senior_rejected", total_rejected)

        top_sources = summary_dict.get("top_sources", ["MockSource"])
        top_companies = summary_dict.get("top_companies", [])

        sources_str = ", ".join(top_sources) if top_sources else "N/A"
        companies_str = ", ".join(top_companies[:5]) if top_companies else "N/A"

        embed = {
            "title": "📊 Daily Execution Summary",
            "description": "Daily job search and auto-application execution report.",
            "color": 0x3498DB,  # Blue
            "fields": [
                {"name": "🔍 Jobs Fetched", "value": str(total_fetched), "inline": True},
                {"name": "🛡️ Jobs Filtered", "value": str(total_rejected), "inline": True},
                {"name": "✅ Jobs Applied", "value": str(total_applied), "inline": True},
                {"name": "⏭️ Duplicates Skipped", "value": str(total_skipped), "inline": True},
                {"name": "⛔ Senior Roles Rejected", "value": str(senior_rejected), "inline": True},
                {"name": "📡 Top Sources", "value": sources_str, "inline": False},
                {"name": "🏢 Top Companies", "value": companies_str, "inline": False}
            ],
            "footer": {"text": "JOB-PLY Daily Execution Report"}
        }

        return self.send_webhook({"embeds": [embed]})

    def send_weekly_summary(self, summary_dict: Dict[str, Any]) -> bool:
        """Send weekly performance summary embed."""
        if not self.enable_weekly_summary:
            return False

        total_apps = summary_dict.get("total_applications", 0)
        avg_ats = summary_dict.get("avg_ats_score", 0.0)
        interviews = summary_dict.get("interviews_received", 0)
        top_sources = summary_dict.get("top_sources", [])

        sources_str = ", ".join(top_sources) if top_sources else "N/A"

        embed = {
            "title": "📈 Weekly Performance Report",
            "description": "Weekly performance analytics and ATS tailoring metrics.",
            "color": 0x9B59B6,  # Purple
            "fields": [
                {"name": "📝 Total Weekly Applications", "value": str(total_apps), "inline": True},
                {"name": "🎯 Average ATS Score", "value": f"{avg_ats:.2f}", "inline": True},
                {"name": "🎉 Interviews Received", "value": str(interviews), "inline": True},
                {"name": "🌐 Top Performing Sources", "value": sources_str, "inline": False}
            ],
            "footer": {"text": "JOB-PLY Analytics Engine"}
        }

        return self.send_webhook({"embeds": [embed]})

    def send_interview_prep_alert(self, prep_data: Dict[str, Any]) -> bool:
        """Send Discord alert when interview preparation materials are generated."""
        if not self.enable_interview_prep_alerts:
            return False

        company = prep_data.get("company", "Unknown Company")
        title = prep_data.get("title", "Unknown Role")
        skills = prep_data.get("required_skills", [])
        tools = prep_data.get("required_tools", [])
        responsibilities = prep_data.get("key_responsibilities", "N/A")
        topics = prep_data.get("topics_to_revise", [])
        file_path = prep_data.get("file_path", "")

        skills_str = ", ".join(skills) if skills else "Python, SQL, EDA"
        tools_str = ", ".join(tools) if tools else "Power BI, Tableau, Excel"
        topics_str = ", ".join(topics) if topics else "SQL JOINs, Data Cleaning, Model Validation"

        embed = {
            "title": "🎯 Interview Preparation Materials Ready",
            "description": f"Generated tailored technical interview guide for **{title}** at **{company}**!",
            "color": 0x1ABC9C,  # Teal
            "fields": [
                {"name": "🏢 Company", "value": company, "inline": True},
                {"name": "💼 Role", "value": title, "inline": True},
                {"name": "🛠️ Required Skills", "value": skills_str, "inline": False},
                {"name": "⚙️ Required Tools", "value": tools_str, "inline": False},
                {"name": "📌 Key Responsibilities", "value": responsibilities, "inline": False},
                {"name": "📚 Topics To Revise", "value": topics_str, "inline": False},
                {"name": "📁 Prep Guide File", "value": f"`{file_path}`" if file_path else "Saved in `interview_prep/`", "inline": False}
            ],
            "footer": {"text": "JOB-PLY Technical Interview Preparation Module"}
        }

        return self.send_webhook({"embeds": [embed]})

    def send_error_alert(self, error_message: str, category: str = "Workflow Exception") -> bool:
        """Send urgent system exception alert embed."""
        if not self.enable_error_alerts:
            return False

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        embed = {
            "title": "🚨 System Exception Encountered",
            "description": f"An issue occurred during job-app-agent execution.",
            "color": 0xFF0000,  # Red
            "fields": [
                {"name": "⚠️ Exception Category", "value": category, "inline": True},
                {"name": "⏰ Timestamp", "value": timestamp, "inline": True},
                {"name": "📋 Error Details", "value": f"```text\n{error_message[:1000]}\n```", "inline": False}
            ],
            "footer": {"text": "JOB-PLY Error Monitoring"}
        }

        return self.send_webhook({"embeds": [embed]})
