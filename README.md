# Production-Grade Job Application Agent (`job-app-agent`)

A clean-architecture, modular, and automated job application agent designed for **Shubham** targeting roles in:
- **Data Analytics**
- **Business/Data-focused Analytics**
- **Junior Data Science** (including graduate, trainee, and roles with training/mentorship)

Built following strict software engineering best practices: Pydantic domain models, clean architecture, deterministic filtering, ATS resume tailoring, custom cover letter generation (150–220 words), and application tracking.

---

## 📁 Repository Structure

```text
job-app-agent/
  README.md
  pyproject.toml
  requirements.txt
  main.py

  config/
    settings.yaml        # App, retry, and LLM configuration
    providers.yaml       # API provider keys and endpoints
    filters.yaml         # Deterministic filter criteria (titles, levels, skills, exclusions)
    user_profile.yaml    # Candidate profile (Shubham's education, skills, projects, experience)

  src/
    core/
      __init__.py
      models.py          # Pydantic models (Job, Profile, ResumeVersion, CoverLetter, ApplicationLog, WorkflowJobResult)
      utils.py           # Logging, retries, text cleaning, word counting

    data/
      __init__.py
      profile_manager.py # Load/update user profile data
      resume_builder.py  # ATS resume tailoring & match scoring (0.0 to 1.0)
      cover_letter.py    # Custom cover letter generator (150-220 words)

    jobs/
      __init__.py
      job_sources.py     # Free job APIs (Remotive) & Mock test sources
      job_scraper.py     # HTML/JSON parsing with BeautifulSoup4
      job_filter.py      # Deterministic filtering logic

    application/
      __init__.py
      form_filler.py     # Maps candidate details to application portal fields
      workflow.py        # End-to-end apply flow orchestrator
      tracker.py         # Application database logger & duplicate prevention

  logs/
    applications.log     # Detailed workflow log entries
    errors.log           # Runtime error log entries

  tests/
    test_models.py
    test_filters.py
    test_resume_builder.py
    test_cover_letter.py
    test_workflow.py
```

---

## 🚀 Getting Started

### 1. Installation

Install dependencies using `pip`:

```bash
pip install -r requirements.txt
```

### 2. Configuration & API Keys (Optional)

- Set your Anthropic Claude API key to enable LLM-powered resume tailoring and cover letter generation:
  ```bash
  # Windows PowerShell
  $env:ANTHROPIC_API_KEY="your-api-key-here"

  # Linux / macOS
  export ANTHROPIC_API_KEY="your-api-key-here"
  ```
- *Note*: If `ANTHROPIC_API_KEY` is not set or `--no-llm` is passed, the agent seamlessly uses a high-precision deterministic NLP pipeline.

---

## 💻 Usage

### Run Dry-Run Mode with Mock Job Source

```bash
python main.py --source mock --dry-run
```

### Run Live Mode with Free Public Remotive Job Feed

```bash
python main.py --source remotive --dry-run
```

### Save Output to JSON File

```bash
python main.py --source mock --dry-run --output-json output.json
```

---

## 🧪 Running Tests

Run the complete automated test suite using `pytest`:

```bash
pytest -v tests/
```

---

## 🎯 Filtering & Matching Rules

1. **Include Roles**:
   - Data Analyst, Junior Data Analyst, Business Analyst (data-heavy), Junior Data Scientist, Graduate Data Scientist, Analytics Engineer (junior), Reporting/Insights Analyst.
2. **Experience Level**:
   - Must be entry-level, junior, graduate, trainee, or explicitly mention training/mentorship.
3. **Core Skills**:
   - Python, SQL, Excel, Power BI, Tableau, statistics, ML basics, data cleaning, EDA.
4. **Senior Exclusions**:
   - Automatically excludes Senior, Lead, Principal, Manager, Director roles unless explicitly prefixed with Junior/Graduate/Entry.

---

## 📄 Formatted Output Schema

For each processed job, the agent outputs a structured JSON object matching the required schema:

```json
{
  "job": {
    "title": "Junior Data Analyst",
    "company": "TechMetrics Ltd",
    "location": "London, UK",
    "work_type": "Hybrid",
    "url": "https://example.com/jobs/jr-data-analyst-1"
  },
  "match_reason": "Matched title pattern and junior level criteria with 4 core data skills (Python, SQL, Excel, Power BI).",
  "required_skills": [
    "Python",
    "SQL",
    "Excel",
    "Power BI"
  ],
  "resume_version": {
    "text": "NAME: Shubham\n...",
    "keywords": [
      "Python",
      "SQL",
      "Power BI"
    ],
    "score": 0.84
  },
  "cover_letter": {
    "text": "Dear Hiring Team at TechMetrics Ltd,\n\n...",
    "tone": "professional",
    "length_words": 182
  },
  "application": {
    "status": "prepared",
    "next_actions": "Review prepared application materials"
  }
}
```
