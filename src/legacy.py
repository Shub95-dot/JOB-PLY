"""Import the old tool's application_tracker.json.

Nothing in that file was ever submitted (the old code wrote status "submitted" without
contacting any site), so entries are imported as LEGACY_UNVERIFIED. Real job postings
from it are also re-queued as SHORTLISTED so they get a proper application — unless you
pass requeue=False. Placeholder/fake URLs and search-results pages are dropped.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from src.apply import ats as ats_mod
from src.core.models import Job, Status
from src.core.tracker import Tracker

FAKE = re.compile(r"example\.com|/jobs/[\w-]+-jobs\?|outerjoin\.us/job/\d+$|"
                  r"(wellfound\.com/jobs|builtin\.com/job|remote\.co/job|remotejobslibrary\.com/job|"
                  r"globalremotely\.com/job|cwjobs\.co\.uk/job|technojobs\.co\.uk/job|datasciencejobs\.co\.uk/job|"
                  r"jobs\.ac\.uk/job|jooble\.org/job|adzuna\.co\.uk/job|ai-jobs\.net/job)/[a-z-]+$", re.I)


def _source_id(url: str) -> tuple[str, str]:
    m = re.search(r"linkedin\.com/jobs/view/[\w-]*?(\d{8,})", url)
    if m:
        return "linkedin", m.group(1)
    m = re.search(r"reed\.co\.uk/jobs/[\w-]+/(\d+)", url)
    if m:
        return "reed", m.group(1)
    t = ats_mod.detect(url)
    if t.ats in ats_mod.AUTO_SUPPORTED:
        return t.ats, f"{t.token}/{t.job_id}"
    return "legacy", re.sub(r"[?#].*$", "", url)


def import_legacy(path: Path, tracker: Tracker, requeue: bool = False) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    items = data.values() if isinstance(data, dict) else data
    st = {"imported": 0, "fake_dropped": 0, "duplicates": 0}
    for it in items:
        url = it.get("url", "")
        if not url or FAKE.search(url):
            st["fake_dropped"] += 1
            continue
        src, sid = _source_id(url)
        job = Job(source=src, source_id=sid, title=it.get("job_title", ""), company=it.get("company", ""),
                  url=url, apply_url=url)
        if not tracker.add_found(job):
            st["duplicates"] += 1
            continue
        tracker.update_fields(job.key, ats=ats_mod.detect(url).ats,
                              notes=f"old tool claimed 'submitted' at {it.get('submitted_at','?')} — never verified")
        if requeue:
            tracker.set_status(job.key, Status.NEEDS_MANUAL, "from old tool — never actually submitted")
        else:
            tracker.set_status(job.key, Status.LEGACY_UNVERIFIED, "old tool marked submitted without submitting")
        st["imported"] += 1
    return st
