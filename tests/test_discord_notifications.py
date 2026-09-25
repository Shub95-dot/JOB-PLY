"""Unit tests for DiscordNotifier service and notification workflows."""

import pytest
from unittest.mock import MagicMock, patch
from src.notifications.discord_notifier import DiscordNotifier


@pytest.fixture
def mock_notifier(monkeypatch):
    monkeypatch.setenv("DISCORD_APPLICATIONS_WEBHOOK", "https://discord.com/api/webhooks/12345/test_token")
    notifier = DiscordNotifier(config_path="config/notifications.yaml", enabled=True)
    return notifier


def test_notifier_init(mock_notifier):
    assert mock_notifier.enabled is True
    assert mock_notifier.webhook_url == "https://discord.com/api/webhooks/12345/test_token"
    assert mock_notifier.enable_application_alerts is True
    assert mock_notifier.enable_daily_summary is True


@patch("requests.post")
def test_send_webhook_success(mock_post, mock_notifier):
    mock_response = MagicMock()
    mock_response.status_code = 204
    mock_post.return_value = mock_response

    payload = {"embeds": [{"title": "Test Embed"}]}
    res = mock_notifier.send_webhook(payload)

    assert res is True
    mock_post.assert_called_once_with(
        mock_notifier.webhook_url,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=10
    )


@patch.object(DiscordNotifier, "send_webhook")
def test_send_application_alert_applied(mock_send, mock_notifier):
    mock_send.return_value = True
    job_data = {
        "title": "Junior Data Analyst",
        "company": "Tech Corp",
        "location": "London, UK",
        "work_type": "Hybrid",
        "url": "https://example.com/job/1"
    }

    res = mock_notifier.send_application_alert(job_data, status="applied", ats_score=0.88, source_name="Reed")
    assert res is True
    mock_send.assert_called_once()
    payload = mock_send.call_args[0][0]
    embed = payload["embeds"][0]

    assert "Application Submitted" in embed["title"]
    assert embed["color"] == 0x2ECC71
    fields = {f["name"]: f["value"] for f in embed["fields"]}
    assert fields["🏢 Company"] == "Tech Corp"
    assert fields["💼 Job Title"] == "Junior Data Analyst"
    assert "88%" in fields["🎯 ATS Score"]


@patch.object(DiscordNotifier, "send_webhook")
def test_send_duplicate_alert(mock_send, mock_notifier):
    mock_send.return_value = True
    job_data = {
        "title": "Data Analyst",
        "company": "Analytics Ltd",
        "url": "https://example.com/job/2"
    }

    res = mock_notifier.send_duplicate_alert(job_data)
    assert res is True
    mock_send.assert_called_once()
    payload = mock_send.call_args[0][0]
    embed = payload["embeds"][0]

    assert "Skipped Duplicate Application" in embed["title"]
    assert embed["color"] == 0xF1C40F


@patch.object(DiscordNotifier, "send_webhook")
def test_send_rejection_alert(mock_send, mock_notifier):
    mock_send.return_value = True
    job_data = {
        "title": "Senior Data Scientist",
        "company": "Big Data Co",
        "url": "https://example.com/job/3"
    }

    res = mock_notifier.send_rejection_alert(job_data, reason="Senior keyword found")
    assert res is True
    mock_send.assert_called_once()
    payload = mock_send.call_args[0][0]
    embed = payload["embeds"][0]

    assert "Job Filtered Out" in embed["title"]
    assert embed["color"] == 0xE74C3C


@patch.object(DiscordNotifier, "send_webhook")
def test_send_daily_summary(mock_send, mock_notifier):
    mock_send.return_value = True
    summary = {
        "total_fetched": 30,
        "total_applied": 5,
        "total_skipped": 2,
        "total_rejected": 23,
        "senior_rejected": 15,
        "top_sources": ["LinkedIn", "Reed"],
        "top_companies": ["Tech Corp", "Data Insights"]
    }

    res = mock_notifier.send_daily_summary(summary)
    assert res is True
    mock_send.assert_called_once()
    payload = mock_send.call_args[0][0]
    embed = payload["embeds"][0]

    assert "Daily Execution Summary" in embed["title"]
    fields = {f["name"]: f["value"] for f in embed["fields"]}
    assert fields["🔍 Jobs Fetched"] == "30"
    assert fields["✅ Jobs Applied"] == "5"
    assert fields["⛔ Senior Roles Rejected"] == "15"


@patch.object(DiscordNotifier, "send_webhook")
def test_send_weekly_summary(mock_send, mock_notifier):
    mock_send.return_value = True
    summary = {
        "total_applications": 20,
        "avg_ats_score": 0.86,
        "interviews_received": 3,
        "top_sources": ["LinkedIn", "Remotive"]
    }

    res = mock_notifier.send_weekly_summary(summary)
    assert res is True
    mock_send.assert_called_once()
    payload = mock_send.call_args[0][0]
    embed = payload["embeds"][0]

    assert "Weekly Performance Report" in embed["title"]
    fields = {f["name"]: f["value"] for f in embed["fields"]}
    assert fields["📝 Total Weekly Applications"] == "20"
    assert fields["🎯 Average ATS Score"] == "0.86"


@patch.object(DiscordNotifier, "send_webhook")
def test_send_interview_prep_alert(mock_send, mock_notifier):
    mock_send.return_value = True
    prep_data = {
        "company": "TechMetrics Ltd",
        "title": "Junior Data Analyst",
        "required_skills": ["Python", "SQL", "EDA"],
        "required_tools": ["Power BI", "Excel"],
        "key_responsibilities": "Build dashboards and query databases",
        "topics_to_revise": ["SQL JOINs", "Data Cleaning"],
        "file_path": "interview_prep/TechMetrics_Ltd_Junior_Data_Analyst.md"
    }

    res = mock_notifier.send_interview_prep_alert(prep_data)
    assert res is True
    mock_send.assert_called_once()
    payload = mock_send.call_args[0][0]
    embed = payload["embeds"][0]

    assert "Interview Preparation Materials Ready" in embed["title"]
    assert embed["color"] == 0x1ABC9C
    fields = {f["name"]: f["value"] for f in embed["fields"]}
    assert fields["🏢 Company"] == "TechMetrics Ltd"
    assert "Python, SQL, EDA" in fields["🛠️ Required Skills"]


@patch.object(DiscordNotifier, "send_webhook")
def test_send_error_alert(mock_send, mock_notifier):
    mock_send.return_value = True

    res = mock_notifier.send_error_alert("Network timeout on scraper API", category="Scraping Failure")
    assert res is True
    mock_send.assert_called_once()
    payload = mock_send.call_args[0][0]
    embed = payload["embeds"][0]

    assert "System Exception Encountered" in embed["title"]
    fields = {f["name"]: f["value"] for f in embed["fields"]}
    assert fields["⚠️ Exception Category"] == "Scraping Failure"
    assert "Network timeout on scraper API" in fields["📋 Error Details"]


def test_missing_webhook_disables_notifier(monkeypatch):
    monkeypatch.delenv("DISCORD_APPLICATIONS_WEBHOOK", raising=False)
    notifier = DiscordNotifier(config_path="config/notifications.yaml", enabled=True)

    assert notifier.enabled is False
    res = notifier.send_application_alert({"title": "Role", "company": "Co"})
    assert res is False
