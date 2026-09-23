"""Unit tests for EmailNotifier service and notification workflows."""

import pytest
from unittest.mock import MagicMock, patch
from src.notifications.email_notifier import EmailNotifier


@pytest.fixture
def mock_notifier():
    notifier = EmailNotifier(config_path="config/notifications.yaml", enabled=True)
    return notifier


def test_notifier_init(mock_notifier):
    assert mock_notifier.enabled is True
    assert mock_notifier.provider == "gmail"
    assert mock_notifier.smtp_host == "smtp.gmail.com"
    assert mock_notifier.smtp_port == 587
    assert mock_notifier.recipient_email == "shirodkars127@gmail.com"


@patch("smtplib.SMTP")
def test_send_email_success(mock_smtp, mock_notifier):
    smtp_instance = MagicMock()
    mock_smtp.return_value.__enter__.return_value = smtp_instance

    res = mock_notifier.send_email("Test Subject", "Test Body")

    assert res is True
    smtp_instance.starttls.assert_called_once()
    smtp_instance.login.assert_called_once_with(mock_notifier.username, mock_notifier.password)
    smtp_instance.send_message.assert_called_once()


@patch.object(EmailNotifier, "send_email")
def test_send_application_alert_applied(mock_send, mock_notifier):
    mock_send.return_value = True
    job_data = {
        "title": "Junior Data Analyst",
        "company": "Tech Corp",
        "location": "London, UK",
        "work_type": "Hybrid",
        "url": "https://example.com/job/1"
    }

    res = mock_notifier.send_application_alert(job_data, status="applied")
    assert res is True
    mock_send.assert_called_once()
    subject = mock_send.call_args[0][0]
    body = mock_send.call_args[0][1]

    assert "Applied: Junior Data Analyst at Tech Corp" in subject
    assert "Junior Data Analyst" in body


@patch.object(EmailNotifier, "send_email")
def test_send_application_alert_duplicate(mock_send, mock_notifier):
    mock_send.return_value = True
    job_data = {
        "title": "Data Analyst",
        "company": "Analytics Ltd",
        "url": "https://example.com/job/2"
    }

    res = mock_notifier.send_application_alert(job_data, status="duplicate")
    assert res is True
    subject = mock_send.call_args[0][0]

    assert "Skipped Duplicate" in subject


@patch.object(EmailNotifier, "send_email")
def test_send_application_alert_rejected(mock_send, mock_notifier):
    mock_send.return_value = True
    job_data = {
        "title": "Senior Data Scientist",
        "company": "Big Data Co",
        "reason": "Senior keyword found",
        "url": "https://example.com/job/3"
    }

    res = mock_notifier.send_application_alert(job_data, status="rejected")
    assert res is True
    subject = mock_send.call_args[0][0]

    assert "Filtered Out" in subject


@patch.object(EmailNotifier, "send_email")
def test_send_daily_summary(mock_send, mock_notifier):
    mock_send.return_value = True
    summary = {
        "total_fetched": 25,
        "total_applied": 3,
        "total_skipped": 2,
        "total_rejected": 20,
        "applied_jobs": [
            {"title": "Junior Data Analyst", "company": "Alpha Co", "location": "London"},
            {"title": "BI Analyst", "company": "Beta Ltd", "location": "Remote"}
        ]
    }

    res = mock_notifier.send_daily_summary(summary)
    assert res is True
    subject = mock_send.call_args[0][0]
    body = mock_send.call_args[0][1]

    assert "Applied: 3" in subject
    assert "Total Jobs Fetched: 25" in body
    assert "Junior Data Analyst @ Alpha Co" in body


@patch.object(EmailNotifier, "send_email")
def test_send_weekly_summary(mock_send, mock_notifier):
    mock_send.return_value = True
    summary = {
        "total_applications": 15,
        "top_sources": ["LinkedIn", "Reed"],
        "avg_ats_score": 0.85,
        "interviews_received": 2
    }

    res = mock_notifier.send_weekly_summary(summary)
    assert res is True
    subject = mock_send.call_args[0][0]
    body = mock_send.call_args[0][1]

    assert "15 Applications" in subject
    assert "Interviews Received: 2" in body


@patch.object(EmailNotifier, "send_email")
def test_send_error_alert(mock_send, mock_notifier):
    mock_send.return_value = True

    res = mock_notifier.send_error_alert("Database connection timeout")
    assert res is True
    subject = mock_send.call_args[0][0]
    body = mock_send.call_args[0][1]

    assert "ERROR ALERT" in subject
    assert "Database connection timeout" in body
