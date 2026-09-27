"""Discord notifications via a channel webhook (Server Settings -> Integrations -> Webhooks -> New Webhook).

Put the URL in .env as DISCORD_WEBHOOK_URL. What gets sent is controlled in settings.yaml -> notifications.discord.
  * applied      — one green message per VERIFIED application (with the confirmation text)
  * needs_you    — after each run, the jobs it could NOT apply to and why
  * failed       — submission attempted but no confirmation (red)
  * summary      — end-of-run totals + "could not auto-apply" breakdown
  * errors       — a job source or the run itself broke
  * interview_prep — a prep guide was written for a job you applied to / got an interview for
"""
from __future__ import annotations

import logging
import time
from typing import Any, Iterable, Optional

import requests

from src.core.config import env

log = logging.getLogger("discord")

GREEN, AMBER, RED, BLUE = 0x2E9E5B, 0xE8A317, 0xD64545, 0x3B82F6


def _cut(s: Any, n: int) -> str:
    s = "" if s is None else str(s)
    return s if len(s) <= n else s[: n - 1] + "…"


class DiscordNotifier:
    def __init__(self, cfg: Optional[dict] = None, webhook_url: Optional[str] = None, session=None):
        c = cfg or {}
        # DISCORD_APPLICATIONS_WEBHOOK is the name used by the previous JOB-PLY version — both work
        self.url = webhook_url if webhook_url is not None else (env("DISCORD_WEBHOOK_URL") or env("DISCORD_APPLICATIONS_WEBHOOK"))
        self.enabled = bool(c.get("enabled", True)) and bool(self.url)
        self.on = {k: bool(c.get(k, True)) for k in ("applied", "needs_you", "failed", "summary", "errors", "interview_prep")}
        self.mention = f"<@{c['mention_user_id']}> " if c.get("mention_user_id") else ""
        self.session = session or requests.Session()
        if c.get("enabled", True) and not self.url:
            log.info("Discord: DISCORD_WEBHOOK_URL (or DISCORD_APPLICATIONS_WEBHOOK) not set — Discord notifications off")

    # ------------------------------------------------------------------ transport
    def _post(self, embeds: list[dict], content: str = "") -> bool:
        if not self.enabled:
            return False
        payload = {"username": "Job Agent", "content": _cut(content, 1900), "embeds": embeds[:10],
                   "allowed_mentions": {"parse": ["users"]}}
        for attempt in range(3):
            try:
                r = self.session.post(self.url, json=payload, timeout=15)
                if r.status_code == 429:  # rate limited
                    wait = float((r.json() or {}).get("retry_after", 2))
                    time.sleep(min(wait, 30))
                    continue
                if r.status_code >= 300:
                    log.warning("Discord webhook %s: %s", r.status_code, _cut(getattr(r, "text", ""), 200))
                    return False
                return True
            except Exception as e:
                log.warning("Discord send failed: %s", e)
                time.sleep(2)
        return False

    # ------------------------------------------------------------------ events
    def applied(self, r) -> bool:
        if not self.on["applied"]:
            return False
        fields = [
            {"name": "Company", "value": _cut(r["company"], 256) or "—", "inline": True},
            {"name": "Type", "value": _cut(f"{r['work_type'] or '—'} · {r['location'] or ''}", 256), "inline": True},
            {"name": "Via", "value": f"{r['source']} → {r['ats']}", "inline": True},
            {"name": "Confirmation", "value": _cut(r["confirmation_text"] or "confirmed by you", 1024)},
        ]
        if r["follow_up_date"]:
            fields.append({"name": "Follow up", "value": r["follow_up_date"], "inline": True})
        return self._post([{"title": _cut(f"✅ Applied: {r['title']}", 256), "url": r["apply_url"] or r["url"],
                            "color": GREEN, "fields": fields}])

    def failed(self, r) -> bool:
        if not self.on["failed"]:
            return False
        return self._post([{"title": _cut(f"❌ Not confirmed: {r['title']} — {r['company']}", 256),
                            "url": r["apply_url"] or r["url"], "color": RED,
                            "description": _cut(f"{r['reason']}\nScreenshot: `{r['evidence_dir'] or '-'}`\n"
                                                "Finish it with `python main.py assist`.", 4000)}])

    def needs_you(self, rows: Iterable, why) -> bool:
        rows = list(rows)
        if not rows or not self.on["needs_you"]:
            return False
        embeds = []
        for i in range(0, len(rows), 15):
            chunk = rows[i:i + 15]
            lines = []
            for r in chunk:
                link = r["apply_url"] or r["url"]
                lines.append(f"• [{_cut(r['title'], 70)}]({link}) — {_cut(r['company'], 40)} "
                             f"· {r['work_type'] or '?'}\n  ↳ {_cut(why(r), 120)}")
            embeds.append({"title": f"⚠️ Could not auto-apply ({len(rows)} jobs)" if i == 0 else "…continued",
                           "color": AMBER, "description": _cut("\n".join(lines), 4000)})
        embeds[-1]["footer"] = {"text": "Run: python main.py assist"}
        ok = True
        for j in range(0, len(embeds), 10):
            ok &= self._post(embeds[j:j + 10], self.mention if j == 0 else "")
        return ok

    def summary(self, stats: dict, breakdown: dict[str, int]) -> bool:
        if not self.on["summary"]:
            return False
        fields = [{"name": k, "value": str(v), "inline": True} for k, v in stats.items()]
        if breakdown:
            fields.append({"name": "Could not auto-apply — why",
                           "value": _cut("\n".join(f"{n} × {k}" for k, n in breakdown.items()), 1024)})
        return self._post([{"title": "📊 Run summary", "color": BLUE, "fields": fields[:25]}])

    def interview_prep(self, info: dict, topics: list[str]) -> bool:
        if not self.on["interview_prep"]:
            return False
        fields = [
            {"name": "Your matching skills", "value": _cut(", ".join(info["have"]) or "—", 1024)},
            {"name": "Gaps to close", "value": _cut(", ".join(info["missing"]) or "none detected", 1024)},
            {"name": "Revise first", "value": _cut("\n".join(f"• {t}" for t in topics) or "—", 1024)},
            {"name": "Guide", "value": _cut(f"`{info['path']}`", 1024)},
        ]
        return self._post([{"title": _cut(f"📘 Interview prep: {info['title']} — {info['company']}", 256),
                            "url": info.get("url") or None, "color": BLUE, "fields": fields}])

    def error(self, msg: str) -> bool:
        if not self.on["errors"]:
            return False
        return self._post([{"title": "🛑 Job agent error", "color": RED, "description": _cut(msg, 4000)}], self.mention)


class NullNotifier:
    def __getattr__(self, name):
        return lambda *a, **k: False
