# job-app-agent v2

Finds entry-level UK data roles through official job APIs. It submits applications on the
ATS forms it can handle reliably (Greenhouse, Lever, Ashby) and checks each one. For
everything else it opens the form for you, pre-filled.

**An application is recorded as `applied` only when the employer's confirmation page is
detected (text, URL and screenshots are saved), or when you confirm it yourself in assist
mode.** The tracker refuses to set `applied` any other way.

## What changed from v1 (and why v1 never applied)

| v1 | v2 |
|---|---|
| No submission code at all; wrote `status: submitted` for every job it saw | Playwright submitter for Greenhouse / Lever / Ashby, with confirmation-page verification and screenshot evidence |
| ~15 of 25 "sources" returned hardcoded fake jobs (`example.com`, `wellfound.com/jobs/jr-ds`…) | Real APIs only: Reed, Adzuna, Greenhouse/Lever/Ashby job-board APIs (Remotive optional) |
| LinkedIn scraper gave every job the same invented description ("Required skills: Python, SQL…"), so the filter passed everything | No LinkedIn/Indeed scraping (against their terms; gets accounts restricted). Descriptions come from the posting |
| Duplicates by hashed URL incl. tracking params (35 repeat entries) | Deduped by platform job ID **and** company+title fingerprint across sources |
| Data-entry, annotator, German-language, US-only and senior roles got through | Stricter title/company/location/language/experience filters, each rejection stored with its reason |
| Profile contained an invented job ("Data Solutions Lab, 2023–24") and unverified metrics, which the cover letters used | Profile rebuilt from your real history; metrics only used when you mark a project `verified: true`; letters are checked for invented numbers |
| JSON file tracker, status set without checks | SQLite tracker with an event history per job; `applied` requires evidence |
| Outlook SMTP (basic auth mostly switched off) | Any SMTP server, e.g. Gmail with an app password |

## Job sources (13)

| Group | Sources | Where jobs can be | Key needed |
|---|---|---|---|
| UK aggregators | Reed, Adzuna, Jooble | UK — hybrid and on-site | free keys (Reed, Adzuna, Jooble) |
| Remote boards | Remotive, RemoteOK, Himalayas, Jobicy, Working Nomads, We Work Remotely, Arbeitnow | anywhere in the world, remote only | none |
| Company career boards | Greenhouse, Lever, Ashby (any company you list, plus any found automatically) | remote anywhere, or UK hybrid/on-site | none |

**Location rules** (`config/filters.yaml`):

- **Remote:** accepted from any country. Postings that only hire from regions excluding the UK ("USA only", "Remote - US", "LATAM") are skipped, because they can't legally employ you from the UK. Set `remote_reject_region_locked: false` to apply to those anyway.
- **Hybrid and on-site:** UK only.

**Where applications get submitted automatically:** only Greenhouse, Lever and Ashby forms. A job from any of the 13 sources is auto-submitted if its apply link leads to one of those three. Otherwise it's flagged for assist mode.

**Not included:** LinkedIn, Indeed, Totaljobs, CV-Library and Glassdoor. None of them has a public API, and their terms prohibit bots.

## When it can't apply, it tells you

Every job that isn't auto-submitted gets status `needs_manual` or `failed`, with the reason stored. You see them in three places:

- **`python main.py status`:** a "COULD NOT AUTO-APPLY" count grouped by reason:
  - site can't be auto-submitted (e.g. Workday, Reed);
  - CAPTCHA on the form;
  - form asks a question you haven't answered in `answers.yaml` (the exact question text is listed);
  - submission attempted but not confirmed (with screenshot).
- **Daily summary:** a "Could not auto-apply — why" table, plus every such job with its link, work type, location, source and reason.
- **`python main.py assist`:** walks you through each one.

## Discord notifications

1. In your Discord server, open the channel's settings: **Edit Channel → Integrations → Webhooks → New Webhook → Copy Webhook URL**.
2. Put the URL in `.env` as `DISCORD_WEBHOOK_URL=...`. The old JOB-PLY name `DISCORD_APPLICATIONS_WEBHOOK` also works, so your existing `.env` needs no change.
3. Run `python main.py test-discord`. A test message should appear in the channel.

**What you get** (each type can be switched on or off in `settings.yaml → notifications.discord`):

| Message | When |
|---|---|
| ✅ **Applied**: role, company, type/location, confirmation text, follow-up date | each **verified** application (auto or assist) |
| ⚠️ **Could not auto-apply (N jobs)**: link, company, type and reason for each | end of every run |
| ❌ **Not confirmed**: reason and screenshot folder | a submission with no confirmation page |
| 📊 **Run summary**: new, shortlisted, applied, failed, waiting, and a breakdown by reason | end of every run |
| 🛑 **Error**: which source or command broke | API key wrong, site down, crash |
| 📘 **Interview prep**: your matching skills, gaps and first topics to revise | each verified application, and when you `mark ... interview` |

## Interview prep

For every **verified** application, a guide is written to `data/interview_prep/<Company>_<Role>.md`. It's rebuilt when you run `python main.py mark KEY interview`, or on demand with `python main.py prep KEY`.

Everything in it comes from the real posting and your profile. Nothing is invented:

- the posting's own sentences about duties and requirements;
- for each skill they ask for, which of your projects used it;
- gaps to close;
- revision topics for each skill (SQL window functions, DAX filter context and so on);
- STAR outlines for your projects (results only from `verified: true` projects);
- your publication and DOI;
- questions to ask them.

v1 wrote a guide for every job it saw, including data-entry and fake listings. v2 writes one only for applications that actually went in.

To get @-pinged for "could not apply" and errors, set `mention_user_id` to your Discord user ID. To find it, turn on Developer Mode, then right-click your name → Copy User ID.

## How a run works

```
discover  ->  13 sources (UK aggregators, worldwide remote boards, company ATS boards)
              dedupe -> hard filters -> relevance score vs your CV -> shortlist
              Reed/Adzuna links are followed; if the employer uses Greenhouse/Lever/Ashby,
              that job becomes auto-submittable and the company's board is added for future runs
prepare   ->  cover letter (Claude API if key set, else template), fact-checked against your profile
apply     ->  for Greenhouse/Lever/Ashby jobs: open form, fill from profile + answers.yaml, upload CV,
              STOP if any required question has no configured answer or a CAPTCHA shows,
              otherwise submit and wait for the confirmation page -> applied / failed
assist    ->  everything else (Reed, Workable, company sites, CAPTCHA, unanswered questions):
              opens the page pre-filled; you submit; it records the evidence
digest    ->  data/digest/digest_YYYY-MM-DD.html (+ email if SMTP set)
```

## Setup (about 20 minutes, once)

```bash
python -m venv .venv
.venv\Scripts\activate           # Windows   (source .venv/bin/activate on macOS/Linux)
pip install -r requirements.txt
python -m playwright install chromium
copy .env.example .env           # then fill it in
```

1. **API keys** in `.env`. Both are free:
   - Reed: <https://www.reed.co.uk/developers/jobseeker>
   - Adzuna: <https://developer.adzuna.com>
   - Jooble: <https://jooble.org/api/about>
   - The 7 remote boards need no key.
   - `ANTHROPIC_API_KEY` is optional (better cover letters).
   - `SMTP_*` is optional (digest email).
2. **Your CV**: put the PDF at `data/Shubham_Shirodkar_CV.pdf`, or change `cv_path` in `config/settings.yaml`.
3. **`config/user_profile.yaml`**: check every line. Fill in the TODOs:
   - your LinkedIn URL;
   - the insurance employer;
   - dates, if you want them.

   Mark a project `verified: true` only when its `results` hold real numbers.
4. **`config/answers.yaml`**: replace each `TODO` with your answer:
   - right to work;
   - sponsorship;
   - notice period;
   - salary expectation;
   - relocation / commute;
   - years of experience;
   - driving licence.

   Until you do, any form that requires one of these goes to assist mode and isn't submitted.
5. **`config/sources.yaml`**: add companies you'd like to work for that use Greenhouse, Lever or Ashby.
   - The company's careers page link shows the token, e.g. `job-boards.greenhouse.io/<token>`.
   - Run `python main.py check-boards` to confirm each token works.
6. **Test without submitting:**
   ```bash
   python main.py run --dry-run
   ```
   The browser fills real forms and stops before Submit. Check the screenshots in `data/evidence/<job>/form_filled.png`.
7. When the dry run looks right, set `profile_reviewed: true` in `config/settings.yaml`.

## Daily use

```bash
python main.py run          # find, prepare, auto-submit up to daily_cap (15), write digest
python main.py assist       # ~20–40 min: go through the jobs that need you
python main.py status       # counts + follow-ups due
python main.py show greenhouse:acme/12345     # full record, cover letter, history
python main.py mark reed:5735521 interview    # record replies: responded/interview/rejected/offer
```

### Scheduling (Windows)

Use Task Scheduler → Create Basic Task → Daily 08:30:

- **Action:** `run_daily.bat`
- **Start in:** the project folder
- Set `headless: true` in settings.yaml for unattended runs.

### Your old tracker

```bash
python main.py import-legacy path\to\application_tracker.json            # keeps history, marked UNVERIFIED
python main.py import-legacy path\to\application_tracker.json --requeue  # also queue the real ones for assist
```

The import drops the fake and placeholder URLs and the Reed search-results pages. None of
those entries were ever sent, so `--requeue` lets you actually apply to the real ones.

## Limits

- **Coverage.** Auto-submit covers Greenhouse, Lever and Ashby only. Many UK employers use Workday, SuccessFactors, Taleo or their own portals, and those need accounts or multi-page flows. Reed and LinkedIn "Easy Apply" need your login and are against their terms to automate. All of these go to assist mode.
- **CAPTCHAs.** The tool never tries to solve a CAPTCHA. The job moves to assist mode and you finish it.
- **Unanswered questions.** A question without a rule in `answers.yaml` blocks submission for that job. The digest lists the exact wording so you can add a rule. Answers are never AI-generated.
- **Form layouts change.** ATS forms change occasionally. Failed confirmations show up as `failed` with a screenshot, never as `applied`.
- **Relevance score.** The score ranks postings against your CV. It doesn't predict whether you'll get an interview.

## Tests

```bash
pytest -q
```

57 tests cover the following:

- **Filters:** titles, years of experience, language, excluded companies, and the remote-worldwide / UK hybrid / UK on-site location rules.
- **Tracker:** evidence rules and cross-source deduplication.
- **ATS detection:** URLs for each ATS.
- **Answers:** matching form questions to your answers.
- **Cover letters:** checks against invented numbers and unverified metrics.
- **API parsers:** all 13 sources.
- **Full pipeline:** one end-to-end run.
- **Browser:** Playwright runs on local copies of Greenhouse-, Lever- and Ashby-style forms.
  - Covers successful submit plus confirmation, dry run, unanswered required question, CAPTCHA, and rejected submission.
