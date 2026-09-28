"""Config + environment loading."""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]


def load_yaml(name: str) -> dict[str, Any]:
    path = ROOT / "config" / name
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def load_env() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass


class Settings:
    def __init__(self, data: dict[str, Any] | None = None):
        d = data if data is not None else load_yaml("settings.yaml")
        self.raw = d
        paths = d.get("paths", {})
        self.db_path = ROOT / paths.get("db", "data/tracker.db")
        self.evidence_dir = ROOT / paths.get("evidence", "data/evidence")
        self.digest_dir = ROOT / paths.get("digest", "data/digest")
        self.browser_profile = ROOT / paths.get("browser_profile", "data/browser_profile")
        cv = d.get("cv_path") or env("CV_PATH")
        self.cv_path = Path(cv).expanduser() if cv else None
        if self.cv_path and not self.cv_path.is_absolute():
            self.cv_path = ROOT / self.cv_path
        a = d.get("apply", {})
        self.daily_cap = int(a.get("daily_cap", 15))
        self.min_score = float(a.get("min_score", 0.15))
        self.headless = bool(a.get("headless", False))
        self.delay_seconds = tuple(a.get("delay_between_applications_seconds", [25, 70]))
        self.confirm_timeout_s = int(a.get("confirmation_timeout_seconds", 25))
        self.profile_reviewed = bool(d.get("profile_reviewed", False))
        llm = d.get("llm", {})
        self.llm_model = llm.get("model", "claude-sonnet-5")
        self.follow_up_days = int(d.get("follow_up_days", 7))


def setup_logging(level: str = "INFO") -> None:
    (ROOT / "logs").mkdir(exist_ok=True)
    fmt = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
    logging.basicConfig(
        level=level, format=fmt, datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout),
                  logging.FileHandler(ROOT / "logs" / "agent.log", encoding="utf-8")],
    )
