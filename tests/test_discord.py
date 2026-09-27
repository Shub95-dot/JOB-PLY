from src.core.tracker import Tracker
from src.notify.discord import DiscordNotifier
from src.pipeline import Pipeline
from tests.test_pipeline import FakeSource, jobs


class Hook:
    """Captures webhook POSTs."""
    def __init__(self, codes=None):
        self.posts, self.codes = [], list(codes or [])

    def post(self, url, json=None, timeout=None):
        self.posts.append(json)
        code = self.codes.pop(0) if self.codes else 204

        class R:
            status_code = code
            text = ""
            def json(self_inner):
                return {"retry_after": 0.01}
        return R()


def test_disabled_without_url():
    n = DiscordNotifier({}, webhook_url="", session=Hook())
    assert n.enabled is False and n.error("x") is False


def test_rate_limit_retry():
    h = Hook(codes=[429, 204])
    assert DiscordNotifier({}, webhook_url="https://discord/x", session=h).error("boom")
    assert len(h.posts) == 2


def test_run_sends_applied_needs_you_and_summary(settings, profile, answered_cfg, browser, monkeypatch):
    h = Hook()
    n = DiscordNotifier({"mention_user_id": "123"}, webhook_url="https://discord/x", session=h)
    t = Tracker(settings.db_path)
    pipe = Pipeline(settings, t, profile, sources_cfg={}, answers_cfg=answered_cfg, notifier=n)
    monkeypatch.setattr(pipe, "_route", lambda job: t.update_fields(
        job.key, ats="lever" if job.source == "lever" else "reed", apply_url=job.apply_url or job.url))
    d = pipe.discover([FakeSource(jobs())])
    pipe.prepare(use_llm=False)
    ctx = browser.new_context()
    a = pipe.apply(context=ctx)
    ctx.close()
    pipe.notify_run_end(d, a)

    titles = [e["title"] for p in h.posts for e in p["embeds"]]
    assert titles[0] == "✅ Applied: Graduate Data Analyst"
    applied = h.posts[0]["embeds"][0]
    assert "Application submitted" in [f for f in applied["fields"] if f["name"] == "Confirmation"][0]["value"]
    needs = next(p for p in h.posts if p["embeds"][0]["title"].startswith("⚠️"))
    assert "Junior Data Analyst" in needs["embeds"][0]["description"] and "Delta" in needs["embeds"][0]["description"]
    assert "Site can't be auto-submitted (reed)" in needs["embeds"][0]["description"]
    assert needs["content"].startswith("<@123>")
    summary = h.posts[-1]["embeds"][0]
    assert summary["title"] == "📊 Run summary"
    assert {"name": "Applied this run", "value": "1", "inline": True} in summary["fields"]


def test_source_error_is_reported(settings, profile):
    h = Hook()
    n = DiscordNotifier({}, webhook_url="https://discord/x", session=h)

    class Broken:
        name = "reed"
        def fetch(self):
            raise RuntimeError("401 — check API credentials")
    Pipeline(settings, Tracker(settings.db_path), profile, sources_cfg={}, notifier=n).discover([Broken()])
    assert "reed: 401" in h.posts[0]["embeds"][0]["description"]


def test_old_jobply_env_name_still_works(monkeypatch):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    monkeypatch.setenv("DISCORD_APPLICATIONS_WEBHOOK", "https://discord.com/api/webhooks/1/abc")
    assert DiscordNotifier({}, session=Hook()).enabled


def test_interview_prep_written_and_announced(settings, profile, answered_cfg, browser, monkeypatch):
    h = Hook()
    n = DiscordNotifier({}, webhook_url="https://discord/x", session=h)
    t = Tracker(settings.db_path)
    pipe = Pipeline(settings, t, profile, sources_cfg={}, answers_cfg=answered_cfg, notifier=n)
    monkeypatch.setattr(pipe, "_route", lambda job: t.update_fields(
        job.key, ats="lever" if job.source == "lever" else "reed", apply_url=job.apply_url or job.url))
    pipe.discover([FakeSource(jobs())])
    pipe.prepare(use_llm=False)
    ctx = browser.new_context()
    pipe.apply(context=ctx)
    ctx.close()
    guide = settings.evidence_dir.parent / "interview_prep" / "Acme_Graduate_Data_Analyst.md"
    assert guide.exists()
    text = guide.read_text(encoding="utf-8")
    assert "# Interview prep — Graduate Data Analyst at Acme" in text
    assert "You will use SQL, Python, Excel and Power BI" in text          # pulled from the real posting
    assert "Maternal Health Risk Prediction in Bangladesh" in text
    assert "10.62762/JAIB.2026.495804" in text
    assert "window functions" in text
    prep = [p for p in h.posts if p["embeds"][0]["title"].startswith("📘")]
    assert prep and "Acme" in prep[0]["embeds"][0]["title"]
