"""Work out which application system a URL belongs to."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import parse_qs, urlparse

import requests

log = logging.getLogger("ats")

# ATSs with a known, stable public application form we can fill and verify.
AUTO_SUPPORTED = {"greenhouse", "lever", "ashby"}


@dataclass
class AtsTarget:
    ats: str                    # greenhouse | lever | ashby | workable | reed | linkedin | indeed | other
    token: Optional[str] = None  # company board token / site / org
    job_id: Optional[str] = None
    form_url: Optional[str] = None

    @property
    def auto(self) -> bool:
        return self.ats in AUTO_SUPPORTED and bool(self.form_url)


_PATTERNS = [
    ("greenhouse", re.compile(r"https?://(?:job-boards|boards)(?:\.eu)?\.greenhouse\.io/(?!embed)([\w-]+)/jobs/(\d+)")),
    ("lever", re.compile(r"https?://jobs(?:\.eu)?\.lever\.co/([\w.-]+)/([0-9a-f-]{36})")),
    ("ashby", re.compile(r"https?://jobs\.ashbyhq\.com/([\w.%-]+)/([0-9a-f-]{36})")),
    ("workable", re.compile(r"https?://apply\.workable\.com/([\w-]+)/j/(\w+)")),
]


def detect(url: Optional[str]) -> AtsTarget:
    if not url:
        return AtsTarget("other")
    for ats, pat in _PATTERNS:
        m = pat.search(url)
        if m:
            token, jid = m.group(1), m.group(2)
            host = urlparse(url).netloc
            if ats == "greenhouse":
                form = f"https://{host}/{token}/jobs/{jid}"
            elif ats == "lever":
                form = f"https://{host}/{token}/{jid}/apply"
            elif ats == "ashby":
                form = f"https://jobs.ashbyhq.com/{token}/{jid}/application"
            else:
                form = url
            return AtsTarget(ats, token, jid, form)
    p = urlparse(url)
    q = parse_qs(p.query)
    # Greenhouse embedded on a company careers page: ?gh_jid=123 or embed/job_app?for=token&token=123
    if "greenhouse.io" in p.netloc and "for" in q and "token" in q:
        t, j = q["for"][0], q["token"][0]
        return AtsTarget("greenhouse", t, j, f"https://job-boards.greenhouse.io/{t}/jobs/{j}")
    host = p.netloc.lower()
    for name in ("reed", "linkedin", "indeed", "totaljobs", "cv-library", "adzuna"):
        if name in host:
            return AtsTarget(name)
    return AtsTarget("other", form_url=url)


def resolve(url: Optional[str], session: Optional[requests.Session] = None, timeout: int = 15) -> AtsTarget:
    """Follow redirects (Adzuna/Reed external links) until we land somewhere recognisable."""
    t = detect(url)
    if t.ats in AUTO_SUPPORTED or not url:
        return t
    s = session or requests.Session()
    try:
        r = s.get(url, allow_redirects=True, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        final = detect(r.url)
        if final.ats in AUTO_SUPPORTED:
            return final
        # careers pages often embed the ATS link in the HTML
        for ats, pat in _PATTERNS:
            m = pat.search(r.text or "")
            if m:
                return detect(m.group(0))
        m = re.search(r"greenhouse\.io/embed/job_board/js\?for=([\w-]+)", r.text or "")
        gh = parse_qs(urlparse(r.url).query).get("gh_jid")
        if m and gh:
            return detect(f"https://job-boards.greenhouse.io/{m.group(1)}/jobs/{gh[0]}")
        return final if final.ats != "other" else AtsTarget("other", form_url=r.url)
    except Exception as e:
        log.debug("resolve %s failed: %s", url, e)
        return t
