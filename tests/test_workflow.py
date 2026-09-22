"""Unit tests for ApplicationWorkflow in application/workflow.py."""

import os
import pytest
from src.application.workflow import ApplicationWorkflow


def test_workflow_mock_dry_run(tmp_path):
    tracker_file = str(tmp_path / "test_tracker.json")
    workflow = ApplicationWorkflow(
        tracker_db_path=tracker_file,
        use_llm=False
    )

    results = workflow.run(source_name="mock", dry_run=True, max_jobs=3)

    assert len(results) > 0
    first_result = results[0]

    # Verify structured JSON output matching requirement #7
    assert "job" in first_result
    assert "title" in first_result["job"]
    assert "company" in first_result["job"]
    assert "work_type" in first_result["job"]

    assert "match_reason" in first_result
    assert "required_skills" in first_result

    assert "resume_version" in first_result
    assert "text" in first_result["resume_version"]
    assert "keywords" in first_result["resume_version"]
    assert "score" in first_result["resume_version"]

    assert "cover_letter" in first_result
    assert "text" in first_result["cover_letter"]
    assert "length_words" in first_result["cover_letter"]

    assert "application" in first_result
    assert first_result["application"]["status"] == "prepared"
