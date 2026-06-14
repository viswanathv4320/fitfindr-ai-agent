"""
Agent-level failure-mode test for the FitFindr planning loop (Milestone 5).

The no-results branch never reaches the LLM-backed tools (suggest_outfit /
create_fit_card), so no Groq mocking is needed here — the agent returns early
before any API call. (The tool-level LLM calls are mocked in test_tools.py so
the suite never depends on the Groq API key.)

Run with:
    pytest tests/
"""

import os
import sys

# Allow importing agent.py from the project root when running `pytest tests/`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import agent
from agent import run_agent
from utils.data_loader import get_example_wardrobe


def _stub_llm_tools(monkeypatch):
    """Stub the LLM-backed tools so agent tests stay offline and deterministic."""
    monkeypatch.setattr(agent, "suggest_outfit", lambda item, wardrobe: "Looks great with jeans.")
    monkeypatch.setattr(agent, "create_fit_card", lambda outfit, item: "Thrifted gem!")


def test_agent_no_results_returns_early():
    # This query matches nothing even after the retry loosens filters, so the
    # agent should stop after search and never style anything.
    session = run_agent("designer ballgown size XXS under $5", get_example_wardrobe())

    assert session["error"]                       # a helpful error is set
    assert session["retry_attempted"] is True     # the retry was tried first
    assert session["search_results"] == []        # no listings found
    assert session["selected_item"] is None       # nothing selected
    assert session["outfit_suggestion"] is None   # suggest_outfit never ran
    assert session["fit_card"] is None            # create_fit_card never ran
    # price_comparison must NOT run on the no-results path.
    assert not session.get("price_assessment")    # stays None / unset


def test_agent_success_sets_price_assessment(monkeypatch):
    # A normal search should produce a readable price assessment.
    _stub_llm_tools(monkeypatch)
    session = run_agent("vintage denim", get_example_wardrobe())

    assert session["selected_item"] is not None
    assert isinstance(session["price_assessment"], str)
    assert session["price_assessment"].strip() != ""
    # The string should talk about price / a deal / similar listings.
    text = session["price_assessment"].lower()
    assert any(word in text for word in ("price", "deal", "similar", "$"))


def test_agent_retry_succeeds_after_strict_price(monkeypatch):
    # "under $20" matches no denim (cheapest is $24), so the first search is
    # empty; the retry bumps the price 25% to $25 and finds the shorts.
    _stub_llm_tools(monkeypatch)

    session = run_agent("vintage denim under $20", get_example_wardrobe())

    assert session["retry_attempted"] is True
    assert session["retry_params"]["max_price"] == 25.0    # 20 * 1.25
    assert session["retry_message"]                        # user-facing note set
    assert session["search_results"]                       # retry found items
    assert session["selected_item"] is not None
    assert session["outfit_suggestion"] == "Looks great with jeans."
    assert session["fit_card"] == "Thrifted gem!"
    assert session["price_assessment"]                     # price check ran too
    assert session["error"] is None


# ── Style profile memory (stretch) ────────────────────────────────────────────

def test_style_profile_is_stored(monkeypatch):
    # A: detected styles, colors, and budget are remembered.
    _stub_llm_tools(monkeypatch)
    session = {}
    run_agent("I like vintage black streetwear under $30", get_example_wardrobe(), session)

    profile = session["style_profile"]
    assert "vintage" in profile["preferred_styles"]
    assert "streetwear" in profile["preferred_styles"]
    assert "black" in profile["preferred_colors"]
    assert profile["budget_preference"] == 30.0


def test_style_profile_no_duplicates(monkeypatch):
    # B: saying "vintage" across two queries stores it only once.
    _stub_llm_tools(monkeypatch)
    session = {}
    run_agent("vintage tee", get_example_wardrobe(), session)
    run_agent("vintage jacket", get_example_wardrobe(), session)

    assert session["style_profile"]["preferred_styles"].count("vintage") == 1


def test_style_memory_is_reused_on_vague_query(monkeypatch):
    # C: prefs from query 1 are folded into a vague query 2's search.
    _stub_llm_tools(monkeypatch)
    session = {}
    run_agent("I like vintage black streetwear under $30", get_example_wardrobe(), session)
    run_agent("find me anything", get_example_wardrobe(), session)

    assert session["style_memory_message"].startswith("Using saved style preferences")
    desc = session["search_description"]
    assert "vintage" in desc and "streetwear" in desc and "black" in desc


def test_style_memory_does_not_override_explicit_item(monkeypatch):
    # New: an explicit item word keeps the search focused; memory is only noted.
    _stub_llm_tools(monkeypatch)
    session = {}
    run_agent("I like vintage black streetwear under $30", get_example_wardrobe(), session)
    run_agent("find me a jacket", get_example_wardrobe(), session)

    desc = session["search_description"]
    assert "jacket" in desc
    assert "streetwear" not in desc          # memory terms not appended
    assert session["style_memory_message"].startswith("Remembered style profile")


def test_style_memory_message_empty_when_no_change(monkeypatch):
    # D: a query that already contains its own keywords adds nothing.
    _stub_llm_tools(monkeypatch)
    session = {}
    run_agent("vintage denim", get_example_wardrobe(), session)

    assert session["style_memory_message"] == ""
