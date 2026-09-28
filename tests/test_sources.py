"""Source parsers against recorded API response shapes (no network)."""
from src.jobs.sources.aggregators import AdzunaSource, ReedSource
from src.jobs.sources.ats_boards import AshbySource, GreenhouseSource, LeverSource


class Resp:
    def __init__(self, data, code=200):
        self.data, self.status_code = data, code

    def json(self):
        return self.data

    def raise_for_status(self):
        pass


class Sess:
    def __init__(self, routes):
        self.routes, self.headers, self.calls = routes, {}, []

    def get(self, url, **kw):
        self.calls.append((url, kw))
        for k, v in self.routes.items():
            if k in url:
                return Resp(v)
        return Resp({}, 404)


def test_reed():
    s = Sess({"/search": {"results": [{"jobId": 55, "employerName": "Delta", "jobTitle": "Junior Data Analyst",
                                        "locationName": "Southampton", "minimumSalary": 28000, "maximumSalary": 32000,
                                        "jobDescription": "<p>SQL &amp; Python</p>", "jobUrl": "https://www.reed.co.uk/jobs/x/55"}]},
              "/jobs/55": {"jobDescription": "<p>Full description with SQL</p>", "externalUrl": "https://jobs.lever.co/delta/0f7a3b1c-1111-2222-3333-444455556666"}})
    src = ReedSource([{"keywords": "data analyst"}], api_key="k", session=s)
    jobs = src.fetch()
    assert jobs[0].key == "reed:55" and jobs[0].salary == "£28,000–£32,000" and jobs[0].description == "SQL & Python"
    j = src.enrich(jobs[0])
    assert j.apply_url.startswith("https://jobs.lever.co/delta/")
    assert s.calls[0][1]["auth"] == ("k", "")


def test_reed_without_key_skips():
    assert ReedSource([{"keywords": "x"}], api_key="", session=Sess({})).fetch() == []


def test_adzuna():
    s = Sess({"/search/1": {"results": [{"id": "9", "title": "<strong>Data</strong> Analyst", "company": {"display_name": "Eta"},
                                          "location": {"display_name": "London"}, "description": "Hybrid role, SQL",
                                          "redirect_url": "https://www.adzuna.co.uk/jobs/land/ad/9"}]}})
    jobs = AdzunaSource([{"keywords": "data analyst"}], app_id="i", app_key="k", pages=1, session=s).fetch()
    assert jobs[0].title == "Data Analyst" and jobs[0].work_type == "Hybrid"


def test_ats_boards():
    gh = Sess({"boards/acme/jobs": {"jobs": [{"id": 1, "title": "Data Analyst", "location": {"name": "London"},
                                              "content": "&lt;p&gt;SQL&lt;/p&gt;", "absolute_url": "https://acme.com/careers?gh_jid=1"}]}})
    j = GreenhouseSource(["acme"], session=gh).fetch()[0]
    assert j.apply_url == "https://job-boards.greenhouse.io/acme/jobs/1" and j.description == "SQL"
    lv = Sess({"postings/beta": [{"id": "u1", "text": "Data Analyst", "categories": {"location": "London"},
                                  "descriptionPlain": "SQL", "lists": [], "hostedUrl": "https://jobs.lever.co/beta/u1",
                                  "applyUrl": "https://jobs.lever.co/beta/u1/apply", "workplaceType": "hybrid"}]})
    j = LeverSource(["beta"], session=lv).fetch()[0]
    assert j.key == "lever:beta/u1" and j.work_type == "Hybrid"
    ab = Sess({"job-board/gamma": {"jobs": [{"id": "u2", "title": "Data Analyst", "location": "London",
                                             "descriptionPlain": "SQL", "jobUrl": "https://jobs.ashbyhq.com/gamma/u2",
                                             "workplaceType": "OnSite"}]}})
    j = AshbySource(["gamma"], session=ab).fetch()[0]
    assert j.apply_url == "https://jobs.ashbyhq.com/gamma/u2/application"


def test_greenhouse_falls_back_to_eu_host():
    s = Sess({"boards-api.eu.greenhouse.io/v1/boards/policyexpert/jobs": {"jobs": [
        {"id": 42, "title": "Data Analyst", "location": {"name": "Fareham, UK"}, "content": "SQL",
         "absolute_url": "https://job-boards.eu.greenhouse.io/policyexpert/jobs/42"}]}})
    j = GreenhouseSource(["policyexpert"], session=s).fetch()[0]
    assert j.apply_url == "https://job-boards.eu.greenhouse.io/policyexpert/jobs/42"
