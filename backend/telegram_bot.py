"""
Telegram bot for Job Hunter.
Sends job alerts, daily digests, and supports basic commands.
"""
import asyncio
import logging
import re
from zoneinfo import ZoneInfo

# Digest timestamps in Eastern Time (app-wide standard)
LOCAL_TZ = ZoneInfo("America/New_York")
from typing import Optional
from datetime import datetime

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
        logger.warning(f"[Telegram] Failed to send message: {e}")


# Role families (mirrors scraper TITLE_FILTER) — first match wins
_ROLE_FAMILIES: list[tuple[str, list[str]]] = [
    ("Data Analyst",  ["data analyst", "data analytics", "analytics engineer", "reporting analyst"]),
    ("BI",            ["business intelligence", "bi developer", "bi analyst", "bi engineer", "power bi", "tableau"]),
    ("Data Engineer", ["data engineer", "etl", "data platform", "data warehouse", "data architect",
                       "database engineer", "database developer", "sql developer", "big data"]),
    ("DevOps/SRE",    ["devops", "sre", "site reliability", "platform engineer", "cloud engineer"]),
    ("Security",      ["security", "cybersecurity", "infosec", "soc analyst"]),
    ("Java",          ["spring boot", "jakarta"]),  # plus \bjava\b regex below
]
_JAVA_RE = re.compile(r"\bjava\b", re.I)
_DATA_RE = re.compile(r"\bdata\b", re.I)

def _role_family(title: str) -> str:
    t = (title or "").lower()
    for fam, kws in _ROLE_FAMILIES:
        if any(kw in t for kw in kws):
            return fam
    # Wide DE net: both "data" + "engineer" anywhere (Data Systems Engineer etc.),
    # or "Software Engineer, Data Platform" style titles
    if _DATA_RE.search(t) and ("engineer" in t or "software engineer" in t):
        return "Data Engineer"
    if _JAVA_RE.search(t):
        return "Java"
    return "Other"


async def send_scrape_digest(new_jobs: list, total_jobs: int):
    """Send a digest after a scrape completes — including zero-job runs,
    so a missing message always means something is actually broken."""
    if not _bot or not _chat_id:
        print("[Telegram] digest skipped — bot not initialized")
        return

    count = len(new_jobs)
    fam_order = [f for f, _ in _ROLE_FAMILIES] + ["Other"]

    def _country_section(flag: str, name: str, jobs: list) -> list:
        fam_counts: dict = {}
        for j in jobs:
            fam = _role_family(j.get("title", ""))
            fam_counts[fam] = fam_counts.get(fam, 0) + 1
        section = [f"{flag} <b>{name}: {len(jobs)}</b>", "——"]
        section += [f"{fam}: <b>{fam_counts[fam]}</b>" for fam in fam_order if fam_counts.get(fam)]
        return section

    usa_jobs   = [j for j in new_jobs if j.get("country") == "USA"]
    india_jobs = [j for j in new_jobs if j.get("country") == "India"]

    lines = ["🔍 <b>Scrape complete</b>", ""]
    lines += _country_section("🇺🇸", "USA", usa_jobs)
    lines += [""]
    lines += _country_section("🇮🇳", "India", india_jobs)
    lines += [
        "",
        f"This run total: <b>{count}</b>",
        f"Total in DB: <b>{total_jobs:,}</b>",
        datetime.now(LOCAL_TZ).strftime("%b %d, %I:%M%p ET"),
    ]

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
