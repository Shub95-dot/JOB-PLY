"""Answers to application-form questions — only ever from YOUR config, never invented.

A question is matched to a rule in config/answers.yaml by regex on its label.
* answer "TODO"      -> unanswerable; if the field is required the job goes to needs_manual.
* answer "@decline"  -> choose the "Prefer not to say / Decline" option (equal-opportunities questions).
* placeholders       -> {first_name} {last_name} {full_name} {email} {phone} {linkedin} {github}
                        {portfolio} {location} {city} {cover_letter}
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from src.content.profile import Profile

DECLINE_RX = re.compile(r"prefer not|decline|don.?t wish|do not wish|rather not|not to say|not disclose|choose not", re.I)

# Identity fields, checked before the answers.yaml rules. Order matters (first match wins).
IDENTITY = [
    ("first_name", r"^(legal\s+)?first\s*name|^given name|^forename"),
    ("last_name", r"^(legal\s+)?(last|family)\s*name|^surname"),
    ("preferred_name", r"preferred (first )?name"),
    ("full_name", r"^(full\s+)?name\b(?!.*(company|employer|referr|school|university|manager))"),
    ("email", r"e-?mail"),
    ("phone", r"phone|mobile|telephone|contact number"),
    ("linkedin", r"linked\s*in"),
    ("github", r"github"),
    ("portfolio", r"portfolio|personal (web)?site|^website"),
    ("resume", r"resume|cv\b|curriculum"),
    ("cover_letter_file", r"cover letter"),
]


@dataclass
class Resolution:
    value: Optional[str]
    rule: str
    todo: bool = False           # a rule matched but you haven't provided the answer yet
    decline: bool = False
    extras: dict = field(default_factory=dict)


class Answers:
    def __init__(self, cfg: dict, profile: Profile, cover_letter: str = ""):
        self.profile = profile
        c = profile.contact
        self.ctx = {
            "first_name": profile.first_name, "last_name": profile.last_name,
            "preferred_name": profile.data.get("preferred_name") or profile.first_name,
            "full_name": profile.name, "email": c.get("email", ""), "phone": c.get("phone", ""),
            "linkedin": c.get("linkedin", ""), "github": c.get("github", ""),
            "portfolio": c.get("portfolio", "") or c.get("github", ""),
            "location": c.get("location", ""), "city": c.get("city", "") or c.get("location", ""),
            "cover_letter": cover_letter,
        }
        self.rules = []
        for r in cfg.get("rules", []):
            pats = [re.compile(p, re.I) for p in r.get("patterns", [])]
            self.rules.append((r["id"], pats, str(r.get("answer", "TODO"))))

    def resolve(self, label: str, kind: str = "text") -> Resolution:
        lab = re.sub(r"\s+", " ", (label or "")).strip().rstrip("*").strip()
        low = lab.lower()
        # identity fields only apply to short labels ("First name"), not long questions that mention them
        if len(lab) <= 60 and kind in ("text", "email", "tel", "url", "file", "textarea", "combobox"):
            for key, rx in IDENTITY:
                if re.search(rx, low):
                    if key in ("resume", "cover_letter_file"):
                        if kind == "file":
                            return Resolution(key, key)
                        if key == "cover_letter_file" and kind == "textarea":
                            return Resolution(self.ctx["cover_letter"], "cover_letter")
                        continue
                    val = self.ctx.get(key, "")
                    return Resolution(val or None, key, todo=not val)
        for rid, pats, ans in self.rules:
            if any(p.search(lab) for p in pats):
                if ans.strip().upper() == "TODO":
                    return Resolution(None, rid, todo=True)
                if ans.strip() == "@decline":
                    return Resolution(None, rid, decline=True)
                try:
                    return Resolution(ans.format(**self.ctx), rid)
                except (KeyError, IndexError):
                    return Resolution(ans, rid)
        if kind == "file" and ("resume" in low or "cv" in low or not low):
            return Resolution("resume", "resume")
        return Resolution(None, "unknown")


def pick_option(options: list[str], res: Resolution) -> Optional[str]:
    """Choose which visible option matches the resolved answer."""
    opts = [o for o in options if o and o.strip() and not re.fullmatch(r"(please )?select.*|--+|choose.*", o.strip(), re.I)]
    if res.decline:
        for o in opts:
            if DECLINE_RX.search(o):
                return o
        return None
    if res.value is None:
        return None
    v = res.value.strip().lower()
    for test in (lambda o: o.lower() == v,
                 lambda o: o.lower().startswith(v),
                 lambda o: re.search(rf"\b{re.escape(v)}\b", o.lower()) is not None):
        hits = [o for o in opts if test(o.strip())]
        if len(hits) >= 1:
            return hits[0]
    return None
