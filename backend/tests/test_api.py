"""End-to-end API checks on a throwaway SQLite database (see conftest.py).
No model calls, no network: registration, approval, the family grant gate on
the jobs feed, and the base resume built from a Profile.

Run from backend/:  python -m pytest tests -q
"""
import asyncio

import main  # noqa: E402  (env is prepared in conftest.py)
from httpx import ASGITransport, AsyncClient

_loop = asyncio.new_event_loop()
_started = False


def run(coro):
    global _started
    if not _started:
        _loop.run_until_complete(main.startup())
        _started = True
    return _loop.run_until_complete(coro)


def client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test")


ADMIN = {"email": "admin@test.local", "password": "test-pass-123", "name": "Test Admin"}
USER = {"email": "priya@test.local", "password": "test-pass-123", "name": "Priya Nair",
        "desired_roles": ["ServiceNow"]}
PROFILE = {"name": "Priya Nair", "first_name": "Priya", "last_name": "Nair", "headline": "",
           "email": "priya@test.local", "phone": "(212) 555-0100", "address": "Austin, TX",
           "linkedin": "priya-nair", "github": "", "website": "",
           "experience": [{"role": "ServiceNow Developer", "company": "Acme", "location": "Austin, TX",
                           "start_date": "Jan 2022", "end_date": "Present", "years": 3,
                           "bullets": ["Built ITSM catalog flows for 40 teams."]}],
           "education": [{"degree": "BS Computer Science", "school": "UT Austin", "year": "2019"}],
           "projects": [], "skills": ["ServiceNow", "JavaScript"], "certifications": []}


async def _register(c, body):
    r = await c.post("/api/auth/register", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_admin_is_approved_on_register_and_others_are_pending():
    async def go():
        async with client() as c:
            a = await _register(c, ADMIN)
            u = await _register(c, USER)
            assert a["user"]["status"] == "approved"
            assert u["user"]["status"] == "pending"
            r = await c.get("/api/jobs", headers=_auth(u["token"]))
            assert r.status_code == 403 and "pending" in r.text.lower()
            return a["token"], u["token"], u["user"]["id"]
    run(go())


def test_approved_user_without_a_family_gets_an_empty_feed():
    async def go():
        async with client() as c:
            a = (await c.post("/api/auth/login", json={"email": ADMIN["email"], "password": ADMIN["password"]})).json()["token"]
            u = (await c.post("/api/auth/login", json={"email": USER["email"], "password": USER["password"]})).json()
            uid = u["user"]["id"]
            r = await c.patch(f"/api/admin/users/{uid}", json={"status": "approved", "job_roles": []}, headers=_auth(a))
            assert r.status_code == 200, r.text
            r = await c.get("/api/jobs", headers=_auth(u["token"]))
            assert r.status_code == 200 and r.json() == []
            # a grant flips the gate open (the feed is still empty: no jobs scraped in tests)
            r = await c.patch(f"/api/admin/users/{uid}", json={"job_roles": ["ServiceNow"]}, headers=_auth(a))
            assert r.status_code == 200
            r = await c.get("/api/settings", headers=_auth(u["token"]))
            assert r.json()["job_roles"] == ["ServiceNow"]
    run(go())


def test_profile_builds_the_users_own_base_resume():
    async def go():
        async with client() as c:
            u = (await c.post("/api/auth/login", json={"email": USER["email"], "password": USER["password"]})).json()
            r = await c.put("/api/profile", json=PROFILE, headers=_auth(u["token"]))
            assert r.status_code == 200, r.text
            resume = (await c.get("/api/settings", headers=_auth(u["token"]))).json()["resume"]
            lines = resume.splitlines()
            assert lines[0] == "Priya Nair — ServiceNow Developer"
            assert lines[1] == "(212) 555-0100 | priya@test.local | linkedin.com/in/priya-nair"
            assert "• Built ITSM catalog flows for 40 teams." in resume
            assert "Senior Data Engineer" not in resume
            r = await c.get("/api/profile/resume/pdf", headers=_auth(u["token"]))
            assert r.status_code == 200 and r.content[:4] == b"%PDF"
            # an explicit headline wins
            r = await c.put("/api/profile", json={**PROFILE, "headline": "Senior ServiceNow Architect"}, headers=_auth(u["token"]))
            assert r.status_code == 200
            resume = (await c.get("/api/settings", headers=_auth(u["token"]))).json()["resume"]
            assert resume.splitlines()[0] == "Priya Nair — Senior ServiceNow Architect"
            assert (await c.get("/api/profile", headers=_auth(u["token"]))).json()["headline"] == "Senior ServiceNow Architect"
    run(go())


def test_stale_fixed_headline_is_rebuilt_at_startup():
    async def go():
        async with client() as c:
            u = (await c.post("/api/auth/login", json={"email": USER["email"], "password": USER["password"]})).json()
            await c.put("/api/profile", json=PROFILE, headers=_auth(u["token"]))
        # simulate a resume saved by the old builder
        async with main.SessionLocal() as db:
            from sqlalchemy import select
            st = (await db.execute(select(main.UserSettings).where(main.UserSettings.user_id == u["user"]["id"]))).scalar_one()
            st.resume = "Priya Nair — Senior Data Engineer\n(212) 555-0100 | priya@test.local | Austin, TX\n\nWORK EXPERIENCE:\n"
            await db.commit()
        assert await main._rebuild_stale_profile_resumes() == 1
        assert await main._rebuild_stale_profile_resumes() == 0      # idempotent
        async with client() as c:
            resume = (await c.get("/api/settings", headers=_auth(u["token"]))).json()["resume"]
            assert resume.splitlines()[0] == "Priya Nair — ServiceNow Developer"
    run(go())
