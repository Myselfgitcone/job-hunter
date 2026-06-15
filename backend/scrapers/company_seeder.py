"""
Seeds the companies table from JSeek's open-source boards.csv.
Runs once on startup if the companies table is empty.

Source: https://raw.githubusercontent.com/colophon-group/jobseek/main/apps/crawler/data/boards.csv
"""
from zoneinfo import ZoneInfo
EST = ZoneInfo('America/New_York')
import httpx
import uuid
import csv
import io
from datetime import datetime, timezone

BOARDS_CSV_URL = "https://raw.githubusercontent.com/colophon-group/jobseek/main/apps/crawler/data/boards.csv"

# ATS name normalizer — maps jseek CSV names → our ATS keys
ATS_MAP = {
    "greenhouse": "greenhouse",
    "lever": "lever",
    "ashby": "ashby",
    "workday": "workday",
    "bamboohr": "bamboohr",
    "smartrecruiters": "smartrecruiters",
    "workable": "workable",
    "recruitee": "recruitee",
}

SUPPORTED_ATS = {"greenhouse", "lever", "ashby", "workday"}


async def seed_companies_if_empty() -> int:
    """
    Fetches JSeek boards.csv and inserts all companies into DB.
    Only runs if companies table is empty.
    Returns number of companies inserted.
    """
    from database import SessionLocal, Company
    from sqlalchemy import select, func

    async with SessionLocal() as db:
        count_result = await db.execute(select(func.count()).select_from(Company))
        count = count_result.scalar()
        if count and count > 0:
            print(f"[CompanySeeder] Already have {count} companies — skipping seed")
            return 0

    print("[CompanySeeder] Companies table empty — fetching JSeek boards.csv...")
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(BOARDS_CSV_URL)
            resp.raise_for_status()
            csv_text = resp.text
    except Exception as e:
        print(f"[CompanySeeder] Failed to fetch boards.csv: {e}")
        # Fall back to seeding from hardcoded scraper lists
        return await _seed_from_hardcoded()

    companies = []
    reader = csv.DictReader(io.StringIO(csv_text))
    for row in reader:
        # JSeek columns: company_slug, board_slug, board_url, monitor_type, monitor_config
        ats_raw = (row.get("monitor_type") or "").lower().strip()
        company_slug = (row.get("company_slug") or "").strip()
        url = (row.get("board_url") or "").strip()
        
        ats = ATS_MAP.get(ats_raw, ats_raw)
        if not company_slug or ats not in SUPPORTED_ATS:
            continue
            
        # Parse monitor_config which looks like '{"token": "1800contacts"}' or '{"slug": "..."}'
        config_str = row.get("monitor_config") or "{}"
        try:
            import json
            config = json.loads(config_str)
            slug = config.get("token") or config.get("slug") or company_slug
        except Exception:
            slug = company_slug

        companies.append({
            "id": str(uuid.uuid4()),
            "name": company_slug.replace("-", " ").title(),
            "ats": ats,
            "slug": slug,
            "careers_url": url,
            "active": True,
            "added_at": datetime.now(EST).isoformat(),
            "source": "jseek_csv",
        })

    if not companies:
        print("[CompanySeeder] CSV parsed but no valid companies found — falling back to hardcoded")
        return await _seed_from_hardcoded()

    async with SessionLocal() as db:
        for c in companies:
            db.add(Company(**c))
        await db.commit()

    print(f"[CompanySeeder] Seeded {len(companies)} companies from JSeek boards.csv")
    return len(companies)


async def _seed_from_hardcoded() -> int:
    """Fallback: seeds from the hardcoded lists in each scraper."""
    from database import SessionLocal, Company
    from scrapers.greenhouse import BOARDS as GH_BOARDS
    from scrapers.ashby import COMPANIES as ASHBY_COMPANIES
    from scrapers.lever import COMPANIES as LEVER_COMPANIES

    now = datetime.now(EST).isoformat()
    companies = []

    for slug in GH_BOARDS:
        companies.append(Company(
            id=str(uuid.uuid4()), name=slug.replace("-", " ").title(),
            ats="greenhouse", slug=slug, active=True, added_at=now, source="hardcoded"
        ))
    for slug in ASHBY_COMPANIES:
        companies.append(Company(
            id=str(uuid.uuid4()), name=slug.replace("-", " ").title(),
            ats="ashby", slug=slug, active=True, added_at=now, source="hardcoded"
        ))
    for slug in LEVER_COMPANIES:
        companies.append(Company(
            id=str(uuid.uuid4()), name=slug.replace("-", " ").title(),
            ats="lever", slug=slug, active=True, added_at=now, source="hardcoded"
        ))

    async with SessionLocal() as db:
        for c in companies:
            db.add(c)
        await db.commit()

    print(f"[CompanySeeder] Fallback: seeded {len(companies)} companies from hardcoded lists")
    return len(companies)
