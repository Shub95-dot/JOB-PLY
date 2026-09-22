"""CLI Entry point for job-app-agent."""

import argparse
import json
import sys
from src.application.workflow import ApplicationWorkflow
from src.core.utils import setup_logger

logger = setup_logger("main")


def main():
    parser = argparse.ArgumentParser(description="job-app-agent: Automated Job Application Engine for Shubham.")
    parser.add_argument(
        "--source",
        type=str,
        default="remotive",
        choices=["mock", "remotive", "rss", "all"],
        help="Job source provider (choices: mock, remotive, rss, all. default: remotive)"
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
        "--output-json",
        type=str,
        default=None,
        help="Path to save output JSON results."
    )

    args = parser.parse_args()

    workflow = ApplicationWorkflow(use_llm=not args.no_llm)
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
