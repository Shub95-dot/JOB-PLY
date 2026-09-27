import pytest

from src.core.models import Job
from src.jobs.filter import JobFilter
from src.jobs.sources.remote_boards import (ArbeitnowSource, HimalayasSource, JobicySource, JoobleSource,
                                            RemoteOKSource, WeWorkRemotelySource, WorkingNomadsSource)
from tests.test_sources import Resp, Sess

D = "We use SQL, Python and Power BI for dashboards and the team works with data every day. " * 3


@pytest.mark.parametrize("src,loc,wt,ok", [
    ("remoteok", "Worldwide", "Remote", True),
    ("remoteok", "Remote", "Remote", True),
    ("remoteok", "", "Remote", True),
    ("jobicy", "EMEA", "Remote", True),
    ("himalayas", "Canada, United Kingdom", "Remote", True),
    ("remoteok", "Remote - US", "Remote", False),
    ("remoteok", "USA only", "Remote", False),
    ("himalayas", "Ukraine", "Remote", False),          # 'uk' inside 'ukraine' must not count
    ("greenhouse", "London, UK", "Hybrid", True),
    ("greenhouse", "Berlin, Germany", "Hybrid", False),
    ("greenhouse", "New York", "On-site", False),
    ("lever", "Toronto", "Unspecified", False),
    ("reed", "Southampton", "Unspecified", True),
    ("jooble", "Leeds", "Hybrid", True),
])
def test_location_rules(src, loc, wt, ok):
    r = JobFilter().evaluate(Job(source=src, source_id="1", title="Junior Data Analyst", company="X",
                                 location=loc, work_type=wt, url="u", description=D))
    assert r.accepted is ok, r.reason


def test_region_locked_can_be_allowed():
    import yaml
    from src.core.config import ROOT
    cfg = yaml.safe_load(open(ROOT / "config" / "filters.yaml"))
    cfg["remote_reject_region_locked"] = False
    r = JobFilter(cfg).evaluate(Job(source="remoteok", source_id="1", title="Data Analyst", company="X",
                                    location="USA only", work_type="Remote", url="u", description=D))
    assert r.accepted


def test_remote_parsers():
    ro = Sess({"remoteok.com/api": [{"legal": "notice"}, {"id": 7, "position": "Data Analyst", "company": "A",
                                     "location": "Worldwide", "description": "<p>SQL</p>", "url": "https://remoteok.com/remote-jobs/7",
                                     "apply_url": "https://jobs.lever.co/a/0f7a3b1c-1111-2222-3333-444455556666"}]})
    j = RemoteOKSource(["data"], session=ro).fetch()[0]
    assert j.key == "remoteok:7" and j.work_type == "Remote" and j.description == "SQL"

    hi = Sess({"himalayas.app": {"jobs": [{"title": "Data Analyst", "companyName": "B", "locationRestrictions": [],
                                           "description": "SQL", "guid": "https://himalayas.app/j/1",
                                           "applicationLink": "https://b.com/apply"}]}})
    j = HimalayasSource(["data analyst"], pages=1, session=hi).fetch()[0]
    assert j.location == "Worldwide"

    jb = Sess({"jobicy.com": {"jobs": [{"id": 3, "jobTitle": "Data Scientist", "companyName": "C", "jobGeo": "Anywhere",
                                        "jobDescription": "SQL", "url": "https://jobicy.com/jobs/3"}]}})
    assert JobicySource(["data"], session=jb).fetch()[0].location == "Anywhere"

    wn = Sess({"workingnomads": [{"title": "BI Analyst", "company_name": "D", "category_name": "Data",
                                  "url": "https://www.workingnomads.com/jobs/bi-analyst-d", "location": "Europe"},
                                 {"title": "Designer", "company_name": "E", "category_name": "Design", "url": "x"}]})
    assert len(WorkingNomadsSource(session=wn).fetch()) == 1

    ab = Sess({"arbeitnow": {"data": [{"slug": "s1", "title": "Data Analyst", "company_name": "F", "remote": True,
                                       "description": "SQL", "url": "https://arbeitnow.com/s1", "location": "Berlin"},
                                      {"slug": "s2", "title": "Data Analyst", "remote": False}], "links": {}}})
    assert [j.source_id for j in ArbeitnowSource(pages=1, session=ab).fetch()] == ["s1"]


def test_wwr_rss():
    rss = b"""<?xml version="1.0"?><rss><channel><item><title>Acme: Junior Data Analyst</title>
    <region>Anywhere in the World</region><link>https://weworkremotely.com/remote-jobs/acme-junior-data-analyst</link>
    <description>&lt;p&gt;SQL&lt;/p&gt;</description></item></channel></rss>"""

    class S(Sess):
        def get(self, url, **kw):
            r = Resp({})
            r.content = rss
            return r
    j = WeWorkRemotelySource(session=S({})).fetch()[0]
    assert (j.company, j.title, j.location) == ("Acme", "Junior Data Analyst", "Anywhere in the World")


def test_jooble_needs_key():
    assert JoobleSource([{"keywords": "x"}], api_key="", session=Sess({})).fetch() == []
