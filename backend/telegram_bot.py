"""
Telegram bot for Job Hunter.
Sends job alerts, daily digests, and supports basic commands.
"""
import asyncio
import logging
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Global bot instance (initialized on startup if token is set)
_bot = None
_chat_id: Optional[str] = None


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


async def send_scrape_digest(new_jobs: list, total_jobs: int):
    """Send a digest after a scrape completes."""
    if not _bot or not _chat_id or not new_jobs:
        return

    count = len(new_jobs)
    lines = [f"🔍 <b>Scrape complete</b> — {count} new job{'s' if count != 1 else ''} found\n"]

    # Show top 5 new jobs
    for job in new_jobs[:5]:
        title = job.get("title", "Unknown")
        company = job.get("company", "")
        location = job.get("location", "")
        source = job.get("source", "")
        url = job.get("url", "")
        loc_str = f" · {location}" if location else ""
        lines.append(f"• <b>{title}</b> @ {company}{loc_str}")
        if url:
            lines.append(f"  <a href='{url}'>Apply →</a>")

    if count > 5:
        lines.append(f"\n<i>...and {count - 5} more. Open Job Hunter to see all.</i>")

    lines.append(f"\n📊 Total jobs in DB: <b>{total_jobs}</b>")
    lines.append(f"🕐 {datetime.now().strftime('%b %d, %H:%M')}")

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
