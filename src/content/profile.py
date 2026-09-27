"""Candidate profile + CV text. The CV you upload is YOUR PDF — this tool never writes a CV."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml

from src.core.config import ROOT


class Profile:
    def __init__(self, data: dict[str, Any]):
        self.data = data
        self.name: str = data["name"]
        self.contact: dict[str, str] = data.get("contact", {})
        self.summary: str = (data.get("summary") or "").strip()
        self.skills: list[str] = _flatten(data.get("skills", {}))
        self.projects: list[dict] = data.get("projects", [])
        self.experience: list[dict] = data.get("experience", [])
        self.education: list[dict] = data.get("education", [])

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "Profile":
        p = path or ROOT / "config" / "user_profile.yaml"
        with open(p, encoding="utf-8") as f:
            return cls(yaml.safe_load(f))

    @property
    def first_name(self) -> str:
        return self.data.get("first_name") or self.name.split()[0]

    @property
    def last_name(self) -> str:
        return self.data.get("last_name") or self.name.split()[-1]

    def verified_projects(self) -> list[dict]:
        return [p for p in self.projects if p.get("verified")]

    def fact_text(self) -> str:
        """Everything the cover-letter writer is allowed to state. Unverified projects contribute
        their title and description but NOT their metrics."""
        parts = [self.name, self.summary, " ".join(self.skills)]
        for e in self.education:
            parts.append(" ".join(str(v) for v in e.values()))
        for e in self.experience:
            parts.append(" ".join(str(v) for k, v in e.items() if k != "highlights"))
            parts.extend(e.get("highlights", []))
        for pub in self.data.get("publications", []):
            parts.append(" ".join(str(v) for v in pub.values()))
        for p in self.projects:
            parts += [p.get("title", ""), p.get("summary", ""), " ".join(p.get("tech", []))]
            if p.get("verified"):
                parts += p.get("results", [])
        return "\n".join(x for x in parts if x)

    def as_text(self) -> str:
        return self.fact_text()


def cv_text(cv_path: Optional[Path], profile: Profile) -> str:
    """Text of the real CV for scoring; falls back to profile facts if the PDF can't be read."""
    if cv_path and cv_path.exists() and cv_path.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader
            text = "\n".join((pg.extract_text() or "") for pg in PdfReader(str(cv_path)).pages)
            if len(text.strip()) > 200:
                return text
        except Exception:
            pass
    return profile.as_text()


def _flatten(skills: Any) -> list[str]:
    if isinstance(skills, list):
        return [str(s) for s in skills]
    out: list[str] = []
    for v in (skills or {}).values():
        out.extend(_flatten(v))
    return out
