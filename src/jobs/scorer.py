"""Relevance score between a posting and your CV (0–1). It's for ranking, not a hiring forecast.

score = 0.6 * skill coverage (share of the posting's recognised skills that you have)
      + 0.4 * TF-IDF cosine similarity between the posting and your CV text (rescaled).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


@dataclass
class Score:
    value: float
    have: list[str]       # skills in the posting that you have
    missing: list[str]    # skills in the posting you don't list — review before applying


class Scorer:
    def __init__(self, cv_text: str, candidate_skills: list[str], vocabulary: list[str]):
        self.cv_text = cv_text
        self.cand = {s.lower() for s in candidate_skills}
        self.vocab = sorted({v.lower() for v in vocabulary} | self.cand)

    def _skills_in(self, text: str) -> set[str]:
        tl = text.lower()
        return {s for s in self.vocab if re.search(rf"(?<![a-z]){re.escape(s)}(?![a-z+#])", tl)}

    def score(self, job_text: str) -> Score:
        req = self._skills_in(job_text)
        have = sorted(req & self.cand)
        missing = sorted(req - self.cand)
        coverage = len(have) / len(req) if req else 0.3
        try:
            vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True)
            m = vec.fit_transform([self.cv_text, job_text])
            cos = float(cosine_similarity(m[0], m[1])[0, 0])
        except ValueError:
            cos = 0.0
        cos_scaled = min(1.0, cos / 0.35)  # typical CV↔JD cosine tops out around 0.3–0.4
        return Score(round(0.6 * coverage + 0.4 * cos_scaled, 3), have, missing)
