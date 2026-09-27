"""Domain models."""
from __future__ import annotations

import hashlib
import re
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Status(str, Enum):
    """Application lifecycle. Only `APPLIED` means an employer actually received an application,
    and the tracker refuses to set it without evidence."""
    FOUND = "found"                    # discovered, not yet evaluated
    FILTERED_OUT = "filtered_out"      # failed hard filters (reason stored)
    SHORTLISTED = "shortlisted"        # passed filters, scored, below daily cap / awaiting materials
    READY = "ready"                    # cover letter prepared, can be auto-submitted (supported ATS)
    NEEDS_MANUAL = "needs_manual"      # needs you: unsupported site, CAPTCHA, or unanswered required question
    APPLIED = "applied"                # VERIFIED submission (confirmation page / your explicit confirmation)
    FAILED = "failed"                  # submit attempted, not confirmed (validation error, timeout...)
    SKIPPED = "skipped"                # you chose not to apply
    RESPONDED = "responded"
    INTERVIEW = "interview"
    REJECTED = "rejected"              # employer rejected
    OFFER = "offer"
    LEGACY_UNVERIFIED = "legacy_unverified"  # imported from the old tool; never proven submitted


# statuses that mean "we are done looking at this posting"
TERMINAL = {Status.FILTERED_OUT, Status.APPLIED, Status.SKIPPED, Status.RESPONDED,
            Status.INTERVIEW, Status.REJECTED, Status.OFFER, Status.LEGACY_UNVERIFIED}


def _norm(s: str) -> str:
    s = s.lower()
    s = re.sub(r"\(.*?\)", " ", s)             # drop "(hybrid)", "(on-site)" etc.
    s = re.sub(r"\b(ltd|limited|plc|llp|inc|uk|group)\b", " ", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


class Job(BaseModel):
    source: str                        # reed / adzuna / greenhouse / lever / ashby / remotive
    source_id: str                     # the platform's own job id
    title: str
    company: str
    location: str = ""
    description: str = ""
    url: str                           # human-readable posting page
    apply_url: Optional[str] = None    # where the application form lives (if known)
    salary: Optional[str] = None
    posted_date: Optional[str] = None
    work_type: str = "Unspecified"     # Remote / Hybrid / On-site / Unspecified

    @property
    def key(self) -> str:
        return f"{self.source}:{self.source_id}"

    @property
    def fingerprint(self) -> str:
        """Cross-source duplicate detection: same company + same normalised title."""
        raw = f"{_norm(self.company)}|{_norm(self.title)}"
        return hashlib.sha1(raw.encode()).hexdigest()[:16]


class FilterResult(BaseModel):
    accepted: bool
    reason: str
    matched_skills: list[str] = Field(default_factory=list)


class ApplyOutcome(BaseModel):
    """Result of one submission attempt."""
    status: Status
    detail: str = ""
    confirmation_text: Optional[str] = None
    evidence_dir: Optional[str] = None
    unanswered: list[str] = Field(default_factory=list)
