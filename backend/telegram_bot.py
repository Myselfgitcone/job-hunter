"""
Telegram bot for Job Hunter.
Sends job alerts, daily digests, and supports basic commands.
"""
import asyncio
import html
import logging
import re
from typing import Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Global bot instance (initialized on startup if token is set)
_bot = None
_chat_id: Optional[str] = None


def is_ready() -> bool:
    return _bot is not None and bool(_chat_id)


async def init_bot(token: str, chat_id: str):
    """Initialize the Telegram bot with token and chat_id."""
    global _bot, _chat_id
    try:
        from telegram import Bot
        _bot = Bot(token=token)
        _chat_id = chat_id
        # Verify connection
        me = await _bot.get_me()
        logger.info(f"[Telegram] Bot connected: @{me.username}")
        return True
    except Exception as e:
        logger.warning(f"[Telegram] Failed to init bot: {e}")
        _bot = None
        return False


async def send_message(text: str, parse_mode: str = "HTML"):
    """Send a message to the configured chat."""
    if not _bot or not _chat_id:
        return
    try:
        await _bot.send_message(chat_id=_chat_id, text=text, parse_mode=parse_mode)
    except Exception as e:
        # HTML parse errors (bad entity in dynamic content) reject the whole
        # message. Retry as plain text so the alert still lands, un-formatted.
        logger.warning(f"[Telegram] {parse_mode} send failed ({e}); retrying as plain text")
        try:
            plain = re.sub(r"<[^>]+>", "", text)
            await _bot.send_message(chat_id=_chat_id, text=plain, parse_mode=None)
        except Exception as e2:
            logger.warning(f"[Telegram] plain-text retry also failed: {e2}")


# Role families (mirrors scraper TITLE_FILTER) — first match wins. Keep in
# sync with fantasticjobs.py: an unlisted scraped family lands in "Other".
_ROLE_FAMILIES: list[tuple[str, list[str]]] = [
    # Leadership first — "Director of Machine Learning" must not fall into DE.
    ("AI/DS Leadership", ["director of ai", "senior director of ai", "head of ai", "vp of ai",
                          "director of data science", "head of data science", "vp of data science",
                          "director of machine learning", "head of machine learning",
                          "chief ai officer", "chief data scientist", "chief data officer",
                          "principal data scientist", "principal machine learning",
                          "ai governance", "responsible ai", "head of ai engineering",
                          "director of ai engineering", "director, ai engineering",
                          "head of data platform", "director of data platform", "vp of data platform",
                          "director, data platform", "director of data engineering",
                          "head of data engineering", "vp of data engineering",
                          "director, data engineering"]),
    # Niche tool-stack families — before the analyst/BI nets so "Epic Clarity
    # Report Analyst" / "Anaplan Analyst" don't fall into wider nets.
    ("Niche - Epic Cogito", ["cogito", "caboodle", "epic clarity", "epic radar",
                             "epic reporting", "epic bi", "epic business intelligence",
                             "clarity report", "slicerdicer", "slicer dicer",
                             "reporting workbench"]),
    ("Niche - Anaplan",     ["anaplan", "connected planning", "onestream",
                             "adaptive planning", "workday adaptive", "pigment planning"]),
    # Entry-level family — before Data Analyst so "Cyber Risk
    # Analyst" doesn't fall into wider analyst nets. (Security/SIEM,
    # GenAI/RAG, and IAM retired.)
    ("GRC",             ["grc", "it risk", "it compliance", "compliance analyst", "risk analyst",
                         "information security analyst", "security compliance", "it auditor",
                         "it audit", "cyber risk", "third party risk", "third-party risk",
                         "vendor risk", "tprm"]),
    ("Data Analyst",    ["data analyst", "data analytics", "analytics engineer", "reporting analyst",
                         "quantitative analyst"]),
    ("BI",              ["business intelligence", "bi developer", "bi analyst", "bi engineer", "power bi", "tableau"]),
    ("Data Engineer",   ["data engineer", "etl", "data platform", "data warehouse", "data architect",
                         "database engineer", "database developer", "sql developer", "big data",
                         "data infrastructure", "data operations engineer",
                         "databricks", "snowflake", "spark", "dbt", "mlops",
                         "machine learning", "ml engineer"]),
    ("Cloud",           ["cloud engineer", "cloud infrastructure", "cloud operations", "cloudops",
                         "cloud systems", "cloud developer", "cloud native", "cloud migration",
                         "aws engineer", "azure engineer", "gcp engineer", "google cloud engineer",
                         "infrastructure engineer", "kubernetes", "terraform"]),
    ("DevOps / SRE",    ["devops", "devsecops", "sre", "site reliability", "platform engineer",
                         "release engineer", "ci/cd", "build engineer", "production engineer",
                         "reliability engineer", "observability"]),
    ("Business Analyst",["business analyst", "business systems analyst", "technical business analyst",
                         "systems analyst", "it business analyst", "business data analyst",
                         "data business analyst", "process analyst", "requirements analyst",
                         "functional analyst"]),
    # O2Ten curated list — bucketed by SOURCE in count_families, never by title
    # (its titles span arbitrary author-invented sections). Empty kws = the
    # title matcher can never claim it; the entry exists so digests list it.
    ("O2Ten", []),
]
_DATA_RE = re.compile(r"\bdata\b", re.I)
_ANALYST_RE = re.compile(r"\banalyst\b", re.I)
_ENGINEER_RE = re.compile(r"\bengineer\b", re.I)

# Mirrors the frontend _isAILeadership regex (App.tsx) so the digest buckets
# leadership the same way the app does — otherwise phrasings like "Director, AI &
# Data Science" or "Head, AI Engineering" leaked into "Other".
_LEAD_RE = re.compile(
    r"((director|head|\bvp\b|vice\s+president|chief|senior\s+director|sr\s+director|principal|staff)"
    r"[\w\s,\-&/]*\b(ai|artificial\s+intelligence|data\s+scien\w*|data\s+platform|data\s+engineering"
    r"|machine\s+learning|\bml\b|applied\s+ai|ml\s+platform|ai\s+platform|mlops|ai\s+governance|responsible\s+ai)\b)"
    r"|(\b(ai\s+platform|artificial\s+intelligence|data\s+scien\w*|machine\s+learning|data\s+platform|data\s+engineering)\b"
    r"[\w\s,\-&/]*\b(director|head|vice\s+president|\bvp\b|chief|principal)\b)"
    r"|chief\s+ai\s+officer|chief\s+data\s+scientist|chief\s+data\s+officer",
    re.I)

def _role_family(title: str) -> str:
    t = (title or "").lower()
    # Leadership first — same matcher the app uses, so counts agree.
    if _LEAD_RE.search(t):
        return "AI/DS Leadership"
    for fam, kws in _ROLE_FAMILIES:
        if any(kw in t for kw in kws):
            return fam
    # Wide nets: both words anywhere in the title
    if _DATA_RE.search(t) and _ANALYST_RE.search(t):
        return "Data Analyst"
    if _DATA_RE.search(t) and _ENGINEER_RE.search(t):
        return "Data Engineer"
    return "Other"


def count_families(jobs: list) -> tuple[dict, list]:
    """Bucket a list of job dicts by role family. Returns (fam_counts, other_titles)."""
    fam_counts: dict = {}
    other_titles: list = []
    for j in jobs:
        if (j.get("source") or "") == "O2Ten":
            fam_counts["O2Ten"] = fam_counts.get("O2Ten", 0) + 1
            continue
        fam = _role_family(j.get("title", ""))
        fam_counts[fam] = fam_counts.get(fam, 0) + 1
        if fam == "Other":
            other_titles.append((j.get("title") or "?").strip())
    return fam_counts, other_titles


def _fmt_family_lines(fam_counts: dict) -> list:
    """Alphabetical 'Family: <n>' lines — EVERY named family listed, zeros
    included. "Other" never shown."""
    fam_order = sorted(f for f, _ in _ROLE_FAMILIES)
    return [f"{fam}: <b>{fam_counts.get(fam, 0)}</b>" for fam in fam_order]


async def send_category_digest(
    heading: str,
    fam_counts: dict,
    total: int,
    *,
    total_db: Optional[int] = None,
    total_app: Optional[int] = None,
    empty_note: Optional[str] = None,
):
    """Category-count digest (hourly + 24h). named families
    only — jobs that land in DB but aren't app-visible ("Other") are excluded
    from the lines AND the Total. "In app" = app-visible jobs in the whole DB;
    "In DB" = raw row count. Sent even on zero-job windows, so a silent bot
    always means something is actually broken."""
    if not _bot or not _chat_id:
        print("[Telegram] digest skipped — bot not initialized")
        return

    vis = {k: v for k, v in (fam_counts or {}).items() if k != "Other"}
    vis_total = sum(vis.values())

    lines = [heading, "——"]
    lines += _fmt_family_lines(vis)   # every family listed, zeros included
    lines += ["", f"Total: <b>{vis_total}</b>"]
    if total_app is not None:
        lines.append(f"In app: <b>{total_app:,}</b>")
    if total_db is not None:
        lines.append(f"In DB: <b>{total_db:,}</b>")
    lines.append(datetime.now(timezone.utc).strftime("%b %d, %H:%M UTC"))

    await send_message("\n".join(lines))


async def send_daily_digest(stats: dict):
    """Send a daily summary."""
    if not _bot or not _chat_id:
        return

    text = (
        f"📋 <b>Daily Job Hunt Summary</b>\n\n"
        f"📌 Total jobs: <b>{stats.get('total', 0)}</b>\n"
        f"✅ Applied: <b>{stats.get('applied', 0)}</b>\n"
        f"🎉 Interviews: <b>{stats.get('interview', 0)}</b>\n"
        f"🆕 New today: <b>{stats.get('new_today', 0)}</b>\n\n"
        f"Keep going! 💪"
    )
    await send_message(text)


async def send_interview_alert(job_title: str, company: str):
    """Alert when a job moves to interview stage."""
    if not _bot or not _chat_id:
        return
    text = (
        f"🎉 <b>Interview stage!</b>\n\n"
        f"<b>{job_title}</b> at <b>{company}</b>\n\n"
        f"Time to prep! Open Job Hunter for interview tips."
    )
    await send_message(text)


async def test_connection(token: str, chat_id: str) -> tuple[bool, str]:
    """Test bot token and chat_id, returns (success, message)."""
    try:
        from telegram import Bot
        bot = Bot(token=token)
        me = await bot.get_me()
        await bot.send_message(
            chat_id=chat_id,
            text=(
                f"✅ <b>Job Hunter connected!</b>\n\n"
                f"Hi! I'm @{me.username}, your job hunt assistant.\n"
                f"I'll notify you about new jobs, interviews, and daily summaries."
            ),
            parse_mode="HTML"
        )
        return True, f"Connected as @{me.username}"
    except Exception as e:
        return False, str(e)
