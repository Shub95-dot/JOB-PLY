"""CLI Entry point for job-app-agent."""

import os
import argparse
import json
import sys
from dotenv import load_dotenv
from src.application.workflow import ApplicationWorkflow
from src.core.utils import setup_logger

load_dotenv()

logger = setup_logger("main")


def validate_environment():
    """Validates required environment variables at startup and prints status."""
    print("=========================================")
    print("STARTUP ENVIRONMENT VALIDATION")
    print("=========================================")

    discord_webhook = os.environ.get("DISCORD_APPLICATIONS_WEBHOOK")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")

    if discord_webhook:
        print("[OK] Discord webhook loaded")
    else:
        print("[WARNING] Missing variable: DISCORD_APPLICATIONS_WEBHOOK")

    if anthropic_key:
        print("[OK] Anthropic key loaded")
    else:
        print("[WARNING] Missing variable: ANTHROPIC_API_KEY")
    print("=========================================\n")


def main():
    parser = argparse.ArgumentParser(description="job-app-agent: Automated Job Application Engine for Shubham.")
    parser.add_argument(
        "--source",
        type=str,
        default="all",
        choices=[
            # Grouped choices
            "all", "remote_all", "hybrid_uk", "onsite_uk",
            # Remote (Worldwide)
            "remotive", "rss", "aijobsnet", "outerjoin", "remoteok", "weworkremotely",
            "himalayas", "remoteco", "wellfound", "builtin", "remotejobslibrary", "globalremotely",
            # Hybrid (UK)
            "linkedin", "indeed", "reed", "totaljobs", "cvlibrary",
            "indeed_hybrid", "reed_hybrid", "totaljobs_hybrid", "cvlibrary_hybrid",
            "cwjobs", "technojobs", "datasciencejobs", "jobsacuk",
            # Onsite (UK)
            "indeed_onsite", "reed_onsite", "totaljobs_onsite", "cvlibrary_onsite",
            "jooble", "adzuna", "datasciencejobs_onsite",
            # Testing
            "mock"
        ],
        help="Job source provider or group (e.g. remote_all, hybrid_uk, onsite_uk, all. default: all)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Run in dry-run mode without mutating application tracking logs or submitting."
    )
    parser.add_argument(
        "--max-jobs",
        type=int,
        default=None,
        help="Maximum number of raw jobs to fetch and process."
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        default=False,
        help="Disable LLM (Anthropic API) integration and use deterministic rule-based generation."
    )
    parser.add_argument(
        "--notify",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable or disable notifications (default: enabled)."
    )
    parser.add_argument(
        "--output-json",
        type=str,
        default=None,
        help="Path to save output JSON results."
    )

    args = parser.parse_args()

    validate_environment()

    workflow = ApplicationWorkflow(use_llm=not args.no_llm, notify=args.notify)

    if args.notify and workflow.discord_notifier.enabled:
        print("Discord notifications enabled.")
        print("Webhook: Loaded successfully")
        print(f"Daily summary: {'enabled' if workflow.discord_notifier.enable_daily_summary else 'disabled'}")
        print(f"Application alerts: {'enabled' if workflow.discord_notifier.enable_application_alerts else 'disabled'}\n")
    else:
        print("Discord notifications disabled (webhook missing or --no-notify).\n")

    results = workflow.run(
        source_name=args.source,
        dry_run=args.dry_run,
        max_jobs=args.max_jobs
    )

    output_formatted = json.dumps(results, indent=2)
    print("\n" + "="*50)
    print("WORKFLOW RESULTS SUMMARY")
    print("="*50)
    print(output_formatted)

    if args.output_json:
        with open(args.output_json, "w", encoding="utf-8") as f:
            f.write(output_formatted)
        print(f"\nSaved workflow output to {args.output_json}")


if __name__ == "__main__":
    main()
