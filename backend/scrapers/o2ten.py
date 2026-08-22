"""
O2Ten "Immediate Jobs" scraper (immediate-jobs.o2ten.com).

The site is a thin wrapper over PUBLIC Google Docs:
  - GET api.o2ten.com/api/jobs/dates            (auth) -> published days per tier
  - GET api.o2ten.com/api/jobs/{date}?tier=X    (auth) -> embedUrl (a Google Doc)
  - docs.google.com/document/d/{id}/export?format=txt  (NO auth) -> the day's text

Auth = the user's `o2ten_token` (localStorage JWT), stored in Setting
"o2ten_token" via POST /api/admin/o2ten-token. On 401 a Telegram alert asks
the admin to re-paste it; everything else keeps running.

Runs inside the hourly scrape but no-ops unless an un-ingested day exists
(publish times are irregular), so cost is one tiny API call per hour.
The day's doc text is LLM-parsed (flash-lite, ~$0.002) into structured jobs —
sections are whatever headers the author used that day, never hardcoded.
"""
import json
import re
import asyncio
from datetime import datetime, timezone

import httpx

API_BASE = "https://api.o2ten.com/api"
SOURCE = "O2Ten"
_TIERS = ("free", "premium")

_PARSE_SYSTEM = """You turn a daily curated job-list document into JSON.
The document has section headers (role categories, e.g. "IT Support:") followed
by numbered lines. Each numbered line contains one or two URLs, a job title
(in [brackets], (parens), or between dashes), and usually a short skills list.

Return ONLY a JSON array, no prose, one object per job line:
[{"section": "<section header without colon>",
  "title": "<job title>",
  "url": "<the BEST apply url: prefer a direct company/ATS link over a
          linkedin.com/jobs link when the line has both>",
  "skills": "<the skills text after the title, or empty string>"}]
Skip intro/promo lines (social links, discount codes, coaching pitches).
Never invent jobs. Keep every numbered job line, including near-duplicates."""


def _canon_url(url: str) -> str:
    """Canonical apply URL — LinkedIn job links lose their tracking params."""
    m = re.search(r"linkedin\.com/jobs/view/(\d+)", url or "")
    if m:
        return f"https://www.linkedin.com/jobs/view/{m.group(1)}/"
    return (url or "").strip()


def _parse_deterministic(text: str) -> list[dict]:
    """Regex fallback if the LLM parse fails. Handles the three observed line
    shapes: `N. url - [Title](link) - skills` / `N. url (Title)-skills` /
    `N. url -Title-skills`. Section = last seen `Header:` line."""
    jobs, section = [], ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if re.fullmatch(r"[A-Za-z0-9&/ .\-]{3,40}:", line):
            section = line.rstrip(":").strip()
            continue
        m = re.match(r"^\d+\.\s*(.+)$", line)
        if not m or "http" not in line:
            continue
        body = m.group(1)
        urls = re.findall(r"https?://\S+", body)
        if not urls:
            continue
        apply_url = next((u for u in urls if "linkedin.com/jobs" not in u), urls[0])
        # Titles/skills live in the non-URL text — URL hyphens/parens are traps.
        stripped = re.sub(r"https?://\S+", " ", body)
        title = ""
        tm = re.search(r"\[([^\]]+)\]", stripped)
        if not tm:
            for pm in re.finditer(r"\(([^)]{4,80})\)", stripped):
                if pm.group(1).strip():
                    tm = pm
                    break
        if tm:
            title = tm.group(1).strip()
        else:
            dm = re.search(r"-\s*([A-Za-z][^-]{3,60})", stripped)
            title = dm.group(1).strip() if dm else ""
        skills = stripped.rsplit("-", 1)[-1].strip() if stripped.count("-") >= 1 else ""
        if title:
            jobs.append({"section": section, "title": title,
                         "url": apply_url.rstrip(").,"), "skills": skills[:200]})
    return jobs


async def _llm_parse(text: str) -> list[dict]:
    """Primary parse — one flash-lite call over the whole doc."""
    from database import SessionLocal, UserSettings
    from sqlalchemy import select
    from ai.llm import chat, ModelKeys
    async with SessionLocal() as db:
        rows = (await db.execute(select(UserSettings))).scalars().all()
    s = next((r for r in rows if (r.google_api_key or r.anthropic_api_key
                                  or r.openai_api_key or r.ai_api_key)), None)
    if not s:
        raise RuntimeError("no AI keys configured")
    keys = ModelKeys(anthropic=s.anthropic_api_key or "", google=s.google_api_key or "",
                     openai=s.openai_api_key or "", openrouter=s.ai_api_key or "")
    raw = await chat(system=_PARSE_SYSTEM, user=text[:60000],
                     api_key=s.ai_api_key or "", provider=s.ai_provider or "openrouter",
                     model="google/gemini-2.5-flash-lite", max_tokens=20000,
                     keys=keys, pass_name="o2ten_parse")
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    return json.loads(m.group()) if m else []


async def fetch(settings: dict) -> list[dict]:
    """Ingest any not-yet-ingested O2Ten days. Returns JobData dicts."""
    from database import SessionLocal, Setting
    from scrapers.base import JobData

    token = (settings.get("o2ten_token") or "").strip()
    if not token:
        return []

    async with SessionLocal() as db:
        row = await db.get(Setting, "o2ten_ingested")
        ingested = set(json.loads(row.value)) if row and row.value else set()

    headers = {"Authorization": f"Bearer {token}"}
    jobs_out: list[dict] = []
    newly_ingested: list[str] = []

    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
        r = await client.get(f"{API_BASE}/jobs/dates", headers=headers)
        if r.status_code == 401:
            # Token expired — alert once per day via telegram, keep running.
            try:
                import telegram_bot
                async with SessionLocal() as db:
                    arow = await db.get(Setting, "o2ten_401_alerted")
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                if not arow or arow.value != today:
                    await telegram_bot.send_message(
                        "⚠️ <b>O2Ten token expired</b> — log in at immediate-jobs.o2ten.com "
                        "and re-paste the token (Settings → O2Ten).")
                    async with SessionLocal() as db:
                        arow = await db.get(Setting, "o2ten_401_alerted")
                        if arow:
                            arow.value = today
                        else:
                            db.add(Setting(key="o2ten_401_alerted", value=today))
                        await db.commit()
            except Exception:
                pass
            print("[O2Ten] token expired (401) — skipping")
            return []
        if r.status_code != 200:
            print(f"[O2Ten] dates HTTP {r.status_code} — skipping")
            return []
        dates = r.json().get("dates", [])

        # Newest few days only. Each (date, tier)
        # ingested exactly once.
        pending = []
        for d in dates[:6]:
            key = f"{d.get('date')}|{d.get('tier')}"
            if d.get("date") and key not in ingested:
                pending.append((d["date"], d.get("tier") or "free", key))
        if not pending:
            return []

        for date_str, tier, key in pending:
            try:
                pr = await client.get(f"{API_BASE}/jobs/{date_str}",
                                      params={"tier": tier}, headers=headers)
                if pr.status_code != 200:
                    continue
                post = pr.json().get("post") or {}
                if post.get("locked"):
                    newly_ingested.append(key)   # not our tier — don't retry forever
                    continue
                doc_m = re.search(r"document/d/([\w-]+)", post.get("embedUrl") or "")
                if not doc_m:
                    newly_ingested.append(key)
                    continue
                doc = await client.get(
                    f"https://docs.google.com/document/d/{doc_m.group(1)}/export",
                    params={"format": "txt"})
                if doc.status_code != 200 or len(doc.text) < 200:
                    continue   # doc not public/ready — retry next hour
                text = doc.text

                try:
                    parsed = await _llm_parse(text)
                    if len(parsed) < 5:
                        raise ValueError(f"LLM returned only {len(parsed)}")
                except Exception as e:
                    print(f"[O2Ten] LLM parse failed ({e}) — deterministic fallback")
                    parsed = _parse_deterministic(text)

                published = (post.get("publishedAt") or "")[:19]
                posted_at = (published + "Z") if published else ""
                # Old backfilled days would be dropped by the scrape-insert
                # posted_at cutoff (60d) — blank it there; the real date stays
                # in the description and the card shows scrape time instead.
                try:
                    _age = (datetime.now(timezone.utc)
                            - datetime.fromisoformat(posted_at.replace("Z", "+00:00"))).days
                    if _age > 55:
                        posted_at = ""
                except Exception:
                    pass
                seen_urls = set()
                kept = 0
                for p in parsed:
                    url = _canon_url(p.get("url") or "")
                    title = (p.get("title") or "").strip()
                    if not url or not title or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    section = (p.get("section") or "General").strip() or "General"
                    skills = (p.get("skills") or "").strip()
                    jobs_out.append(JobData(
                        title=title,
                        company=section,          # curated list has no company — the
                        url=url,                  # section is the most useful label
                        source=SOURCE,
                        description=(f"O2Ten curated list — {date_str} ({tier} tier)\n"
                                     f"Section: {section}\n"
                                     + (f"Skills: {skills}\n" if skills else "")
                                     + f"Apply: {url}"),
                        location="United States",
                        country="USA",
                        posted_at=posted_at,
                    ).to_dict())
                    kept += 1
                print(f"[O2Ten] {date_str} ({tier}): {len(parsed)} parsed → {kept} kept")
                newly_ingested.append(key)
            except Exception as e:
                print(f"[O2Ten] {date_str} ({tier}) failed: {e}")

    if newly_ingested:
        async with SessionLocal() as db:
            row = await db.get(Setting, "o2ten_ingested")
            cur = set(json.loads(row.value)) if row and row.value else set()
            cur.update(newly_ingested)
            keep = sorted(cur)[-60:]   # bound growth
            if row:
                row.value = json.dumps(keep)
            else:
                db.add(Setting(key="o2ten_ingested", value=json.dumps(keep)))
            await db.commit()

    return jobs_out
