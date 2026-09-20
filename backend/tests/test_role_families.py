"""The Data Engineer / AI Engineering two-way wall: a GenAI, LLM, RAG or AI-platform title
belongs ONLY to the AI Engineering family, and an ordinary data-engineering title belongs ONLY
to Data Engineer. The server matcher (main._title_matches_roles), the digest classifier
(telegram_bot._role_family) and the client matcher (App.tsx _isAIEngineering) share one pattern;
this pins the two Python ones. Run from backend/:  python -m pytest tests -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import telegram_bot as tb  # noqa: E402
from main import _ROLE_FAMILY_ITEMS, _roles_families, _title_matches_roles  # noqa: E402

# the two chip groups, exactly as ROLE_GROUPS in JobPreferencesModal.tsx lists them
DE = ["Data Engineer", "ETL Developer", "Data Platform", "Data Warehouse", "Data Architect",
      "Database Engineer", "Database Developer", "SQL Developer", "Software Engineer (Data)",
      "Databricks Engineer", "Snowflake Engineer", "Spark Engineer"]
AI = ["Generative AI Engineer", "GenAI Engineer", "LLM Engineer", "RAG Engineer",
      "AI Platform Engineer", "AI Data Engineer", "AI Infrastructure Engineer",
      "AI Integration Engineer", "AI Solutions Engineer", "Applied AI Engineer",
      "Enterprise AI Engineer", "Data & AI Engineer"]

AI_TITLES = ["GenAI Engineer", "Generative AI Engineer", "Senior GenAI Engineer", "LLM Engineer",
             "Senior LLM Engineer", "RAG Engineer", "Senior RAG Engineer", "AI Platform Engineer",
             "Senior AI Platform Engineer", "AI Data Engineer", "Senior AI Data Engineer",
             "GenAI Data Engineer", "Data & AI Engineer", "Senior Data & AI Engineer",
             "Data/AI Engineer", "AI/Data Engineer", "Data & GenAI Engineer",
             "Data + AI Platform Engineer", "AI/ML Data Engineer", "Data Engineer - AI/ML",
             "Data Engineer - Generative AI", "Data Engineer - AI Platforms", "Data Engineer - LLM/RAG",
             "LLM Platform Engineer", "GenAI Platform Engineer", "Enterprise AI Engineer",
             "Applied AI Engineer", "AI Solutions Engineer", "AI Integration Engineer",
             "LLM Integration Engineer", "AI Infrastructure Engineer"]

DE_TITLES = ["Senior Data Engineer", "Data Engineer", "Data Platform Engineer",
             "Databricks Data Engineer", "ETL Developer", "Snowflake Engineer", "Spark Engineer",
             "Data Architect", "Database Engineer", "SQL Developer", "Big Data Engineer",
             "Data Warehouse Engineer"]

# sales, product, management, science and leadership wording is not an engineering job
NEITHER = ["Pre-Sales AI Solutions Engineer", "AI Solutions Sales Engineer", "AI Engineering Manager",
           "Head of AI Engineering", "Generative AI Product Manager", "AI Research Scientist",
           "Applied AI Scientist", "Platform Engineer", "Site Reliability Engineer",
           "Data Scientist", "AI Engineer", "Test Engineer"]


def test_ai_titles_land_only_in_the_ai_family():
    for t in AI_TITLES:
        assert _title_matches_roles(t, AI), t
        assert not _title_matches_roles(t, DE), t
        assert tb._role_family(t) == "AI Engineering", (t, tb._role_family(t))


def test_data_titles_land_only_in_the_data_family():
    for t in DE_TITLES:
        assert _title_matches_roles(t, DE), t
        assert not _title_matches_roles(t, AI), t
        assert tb._role_family(t) == "Data Engineer", (t, tb._role_family(t))


def test_sales_product_and_leadership_titles_are_in_neither():
    for t in NEITHER:
        assert not _title_matches_roles(t, AI), t
        assert not _title_matches_roles(t, DE), t


def test_the_two_grants_stay_separate_families():
    # the non-admin "one family active at a time" rule depends on this
    assert _roles_families(DE) == {"Data Engineer"}
    assert _roles_families(AI) == {"AI Engineering"}
    assert "AI Engineering" in _ROLE_FAMILY_ITEMS


def test_the_scraper_bills_the_ai_titles_as_their_own_family():
    from scrapers.fantasticjobs import ALL_FAMILIES, _FAMILY_TERMS
    assert "AI Engineering" in ALL_FAMILIES
    assert "genai" in _FAMILY_TERMS["AI Engineering"]
    assert "genai" not in _FAMILY_TERMS["Data Engineer"]
