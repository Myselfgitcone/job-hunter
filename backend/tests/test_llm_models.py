"""Claude 5.5 swap (2026-10-29): rate table, per-generation request fields, and
text extraction by block type. Run from backend/: python -m pytest tests -q
"""
import os
import sys
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.llm import _HAIKU_FALLBACK, _anthropic_params, _rate_for, _text_of  # noqa: E402


def test_rates_match_the_pricing_page():
    assert _rate_for("anthropic/claude-sonnet-5.5") == (2.0, 10.0)
    assert _rate_for("claude-sonnet-5-5") == (2.0, 10.0)
    assert _rate_for("anthropic/claude-haiku-5-5") == (0.10, 0.50)
    assert _rate_for("claude-opus-5-5") == (4.0, 20.0)
    # old ids keep their old price so historical ledgers stay right
    assert _rate_for("anthropic/claude-sonnet-4.6") == (3.0, 15.0)
    assert _rate_for("claude-haiku-4-5") == (1.0, 5.0)
    assert _rate_for("google/gemini-2.5-flash") == (0.30, 2.50)
    # an unknown future id in a family bills at the current generation, never lower
    assert _rate_for("claude-sonnet-6-0") == (2.0, 10.0)


def test_request_fields_per_generation():
    assert _anthropic_params("claude-sonnet-5-5") == {"thinking": {"type": "between_tools"}}
    assert _anthropic_params("claude-sonnet-5.5") == {"thinking": {"type": "between_tools"}}
    assert _anthropic_params("claude-haiku-5-5") == {"thinking": {"type": "disabled"}, "output_config": {"effort": "low"}}
    assert _anthropic_params("claude-opus-5-5") == {"output_config": {"effort": "low"}}
    # 4.x ids are sent exactly as before: no thinking, no effort, and never temperature
    assert _anthropic_params("claude-sonnet-4-6") == {}
    assert _anthropic_params("claude-haiku-4-5") == {}
    assert _HAIKU_FALLBACK == "claude-haiku-4-5"   # 5.5 withdrawn 2026-10-29 pending its own gate


def test_text_is_read_by_block_type_not_position():
    msg = NS(content=[NS(type="thinking", thinking=""), NS(type="text", text="Hello "), NS(type="text", text="world")])
    assert _text_of(msg) == "Hello world"
    assert _text_of(NS(content=[])) == ""
    assert _text_of(NS(content=None)) == ""
