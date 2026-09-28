"""Shared HTTP helper for job sources. Only official/public JSON APIs are used — no HTML scraping."""
from __future__ import annotations

import html
import logging
import re
import time
from abc import ABC, abstractmethod
from typing import Any, Optional

import requests

from src.core.models import Job

log = logging.getLogger("sources")

USER_AGENT = "job-app-agent/2.0 (personal job search; contact via GitHub Shub95-dot)"


class SourceError(RuntimeError):
    pass


class JobSource(ABC):
    name: str = "base"

    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", USER_AGENT)

    @abstractmethod
    def fetch(self) -> list[Job]:
        ...

    def get_json(self, url: str, *, params: dict | None = None, auth=None,
                 retries: int = 1, timeout=(6, 12)) -> Any:
        last: Exception | None = None
        for attempt in range(retries + 1):
            try:
                r = self.session.get(url, params=params, auth=auth, timeout=timeout)
                if r.status_code == 404:
                    raise SourceError(f"404 Not Found: {url}")
                if r.status_code in (401, 403):
                    raise SourceError(f"{r.status_code} — check API credentials for {self.name}")
                r.raise_for_status()
                return r.json()
            except SourceError:
                raise
            except Exception as e:  # network / 5xx / JSON
                last = e
                if attempt < retries:
                    time.sleep(1.5)
        raise SourceError(f"{self.name}: {url} failed after retries: {last}")


def html_to_text(s: str | None) -> str:
    if not s:
        return ""
    s = html.unescape(s)
    if "<" in s:
        from bs4 import BeautifulSoup
        s = BeautifulSoup(s, "html.parser").get_text(" ")
    return re.sub(r"\s+", " ", s).strip()


def infer_work_type(*texts: str) -> str:
    t = " ".join(x or "" for x in texts).lower()
    if "hybrid" in t:
        return "Hybrid"
    if "remote" in t or "work from home" in t:
        return "Remote"
    if "on-site" in t or "onsite" in t or "office based" in t or "office-based" in t:
        return "On-site"
    return "Unspecified"
