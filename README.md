# Job Hunter

Full-stack job search platform: scrapes fresh postings from 55+ ATS platforms
every hour, scores each job against a candidate's resume, tailors the resume
per job description with an LLM pipeline, and tracks the application lifecycle
end to end. Multi-user with per-family role grants and per-user AI scoring.

## Stack

| Layer | Tech |
|---|---|
| Backend | FastAPI (async), SQLAlchemy 2 (asyncpg), APScheduler |
| Frontend | React 18 + TypeScript + Vite |
| Database | PostgreSQL (SQLite fallback for local dev) |
| AI | Anthropic + Google + OpenAI APIs, routed per pass by cost tier |
| Sources | FantasticJobs feed API (ATS + job-board), curated-list ingestion |
| Extras | Chrome extension for application autofill, Telegram digests |
| Deploy | Railway (API) + Vercel (frontend), auto-deploy on push |

## Core features

- **Hourly scraping** with per-family boolean title filters composed at fetch
  time from admin toggles; credit guards pre-check volume via free count
  endpoints before paying per-job fees. Drop-reason counters log a funnel
  (`raw → kept | drops: non_usa:12 board_repost:8 …`) for every run.
- **Role families** — Data Engineer, Data Analyst, BI, Cloud, DevOps/SRE,
  Business Analyst, four entry-level security/AI families, an AI/DS leadership
  family, and a curated-list source. Admin grants families per user; strict
  title matchers keep families from leaking into each other.
- **Resume tailoring** — four-pass LLM pipeline (analyze → tailor → QA fix →
  three-gate scoring) with anti-fabrication linting, deterministic title
  restoration, per-resume cost tracking, and batch mode with prompt caching.
- **Per-user AI match scoring** — every new job is scored against each active
  user's own profile on a low-cost model tier.
- **Experience extraction** — regex over JD text (degree-substitution aware),
  API coarse bands as fallback, AI inference as last resort.
- **Application tracking** — status pipeline (screening/assessment/interview
  rounds/final), Kanban, dashboards, resume history, DOCX/PDF export.
- **Telegram digests** — hourly and daily category counts, app-visible jobs
  only, plus operational alerts (expired tokens, scrape failures).

## Layout

```
backend/
  main.py             API routes, scheduler, scrape orchestration
  database.py         models, migrations, encrypted secret columns
  experience.py       years-of-experience extraction
  telegram_bot.py     digests + alerts
  ai/                 llm routing, tailoring pipeline, qualify, ATS scoring
  scrapers/           fantasticjobs.py (primary), o2ten.py, base helpers
frontend/
  src/App.tsx         shell, filters, role-family matchers
  src/components/     job cards, detail panel, dashboards, settings
extension/            Chrome autofill extension (see extension/README.md)
```

## Local development

```bash
# backend
cd backend
python -m venv venv && venv/Scripts/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# frontend
cd frontend
npm install
npm run dev
```

Environment (backend `.env`): `DATABASE_URL`, `SECRET_KEY`,
`FANTASTIC_JOBS_API_KEY`, OAuth client IDs, `CORS_ORIGIN`. AI provider keys
are entered per user in Settings and stored encrypted at rest.

## Operational notes

- Scrape economy: hourly runs use a 1-hour window so jobs are billed once;
  a forced wider window is available for one-shot backfills.
- Retention: jobs older than 60 days are deleted unless they are in an
  applied/interview stage.
- All timestamps are stored UTC; the scheduler runs on US Eastern crons.
