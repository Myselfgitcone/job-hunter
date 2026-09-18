"""Pure-code tests for the slim pipeline's own guards and the pipeline switch.
Run from backend/:  python -m pytest tests -q
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai import tailor as t  # noqa: E402
from ai import tailor_slim as s  # noqa: E402
from ai.tailor_slim_prompt import TAILOR_SYSTEM_SLIM  # noqa: E402

BASE = """Jane Doe — Data Engineer
jane@example.com

SKILLS:
• Platforms: Databricks, Delta Lake

EXPERIENCE:
Data Engineer @ JPMorgan Chase | New York, NY\tDec 2018 – Dec 2020
• Built scalable Spark and Databricks pipelines on AWS processing hundreds of millions of daily retail-banking transaction records for 10 downstream teams.
• Optimized PySpark ETL frameworks in Databricks through partitioning and caching, saving over $100K per year in cluster spend.

CERTIFICATIONS:
• AWS Certified Cloud Practitioner
"""


def test_cert_guard_removes_credentials_the_base_lacks():
    text = ("Jane Doe — X\n\nSKILLS:\n• AI and ML: LangChain, Databricks Certified Data Engineer Associate, "
            "Databricks Certified Data Engineer Professional\n• Platforms: Databricks\n\n"
            "EXPERIENCE:\nData Engineer @ JPMorgan Chase | NY\t2018 – 2020\n• Built things on Databricks.\n\n"
            "CERTIFICATIONS:\n• AWS Certified Cloud Practitioner\n• Databricks Certified Data Engineer Professional\n")
    notes: list = []
    out = s.strip_unowned_certs(text, BASE, notes)
    assert "Databricks Certified" not in out
    assert "AWS Certified Cloud Practitioner" in out          # the base lists it
    assert "• AI and ML: LangChain" in out
    assert notes and "cert guard" in notes[0]
    # a base with no certifications: the whole section goes
    out2 = s.strip_unowned_certs(text, BASE.split("CERTIFICATIONS:")[0], [])
    assert "CERTIFICATIONS" not in out2 and "Certified" not in out2


def test_magnitudes_and_money_come_back_exactly():
    tailored = BASE.replace("hundreds of millions of daily", "millions of daily").replace("$100K", "100k")
    notes: list = []
    out = s.restore_magnitudes(tailored, BASE, notes)
    assert "hundreds of millions of daily" in out and "$100K" in out and "100k" not in out
    assert notes and "magnitude guard: 2" in notes[0]
    assert s.restore_magnitudes(BASE, BASE, []) == BASE      # nothing to do when intact


def test_switch_defaults_to_slim_and_full_is_the_rollback(monkeypatch):
    calls = []

    async def fake_full(*a, **k):
        calls.append("full"); return "x", {}

    async def fake_slim(*a, **k):
        calls.append("slim"); return "x", {}
    monkeypatch.setattr(t, "tailor_resume", fake_full)
    monkeypatch.setattr(s, "tailor_resume_slim", fake_slim)
    monkeypatch.delenv("TAILOR_PIPELINE", raising=False)
    asyncio.run(s.tailor_resume_routed("b", "j", "k", "p", "m"))
    monkeypatch.setenv("TAILOR_PIPELINE", "full")
    asyncio.run(s.tailor_resume_routed("b", "j", "k", "p", "m"))
    assert calls == ["slim", "full"]


def test_slim_prompt_is_standalone_and_carries_its_rules():
    p = TAILOR_SYSTEM_SLIM
    for rule in ("KEEP WHAT IS TRUE AND SPECIFIC", "NEVER a certification", "never past 30",
                 "hundreds of millions", "insurance-adjacent", "NEVER THROW REAL WORK AWAY"):
        assert rule in p, rule
    assert "one SHORT 8" not in p and "one figure per two" not in p      # the rules the slim pipeline dropped
    assert "{" not in p and "}" not in p
    assert t._TAILOR_SYSTEM_V2 != p and "one SHORT 8" in t._TAILOR_SYSTEM_V2   # the current prompt is untouched


def test_migrated_is_not_stepped_down_on_a_foreign_tool_bullet():
    text = ("Jane Doe — X\n\nEXPERIENCE:\nData Engineer @ Acme | 2018 - 2020\n"
            "• Migrated a legacy SQL Server warehouse to Snowflake for regulatory reporting.\n")
    base = text.replace("Jane Doe — X", "Jane Doe — X\n\nSUMMARY:\n• Engineer with 5+ years.")
    out = t._verb_ladder_guard(text, base, ["Snowflake"], [])
    assert "• Migrated a legacy SQL Server warehouse to Snowflake" in out
