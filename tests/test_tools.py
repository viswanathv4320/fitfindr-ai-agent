"""
Pytest tests for the three FitFindr tools in tools.py.

LLM-backed tools (suggest_outfit, create_fit_card) are tested by monkeypatching
the Groq client, so these tests never make a real API call or need an API key.

Run with:
    pytest tests/
"""

import os
import sys

# Allow importing tools.py from the project root when running `pytest tests/`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tools
from tools import search_listings, suggest_outfit, create_fit_card, price_comparison


# ── Groq mocking helpers ──────────────────────────────────────────────────────

class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, content):
        self._content = content

    def create(self, *args, **kwargs):
        return _FakeResponse(self._content)


class _FakeClient:
    """Stand-in for the Groq client that returns a fixed response."""

    def __init__(self, content):
        self.chat = type("Chat", (), {"completions": _FakeCompletions(content)})()


def _patch_groq(monkeypatch, content):
    """Make tools._get_groq_client() return a fake client with `content`."""
    monkeypatch.setattr(tools, "_get_groq_client", lambda: _FakeClient(content))


def _patch_groq_failure(monkeypatch):
    """Make tools._get_groq_client() raise, simulating a missing key / API error."""
    def _boom():
        raise RuntimeError("simulated Groq failure")

    monkeypatch.setattr(tools, "_get_groq_client", _boom)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def test_search_listings_normal_query_returns_results():
    results = search_listings("vintage denim")
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_listings_no_match_returns_empty_list():
    results = search_listings("zzzzz nonexistent unicorn spaceship")
    assert results == []


def test_search_listings_respects_max_price():
    results = search_listings("vintage denim", max_price=30)
    assert len(results) > 0
    assert all(item["price"] <= 30 for item in results)


def test_search_listings_respects_size_filter():
    results = search_listings("vintage denim", size="M")
    # "M" should match only sizes whose tokens include M (M, S/M, M/L) —
    # never S, L, or waist sizes like W28.
    for item in results:
        tokens = item["size"].upper().replace("/", " ").split()
        assert "M" in tokens


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

SAMPLE_ITEM = {
    "title": "Y2K Baby Tee — Butterfly Print",
    "category": "tops",
    "colors": ["white", "pink", "purple"],
    "style_tags": ["y2k", "vintage", "graphic tee"],
}

SAMPLE_WARDROBE = {
    "items": [
        {"name": "Baggy dark-wash jeans", "category": "bottoms", "colors": ["blue"]},
        {"name": "White sneakers", "category": "shoes", "colors": ["white"]},
    ]
}


def test_suggest_outfit_normal_wardrobe(monkeypatch):
    _patch_groq(monkeypatch, "Pair the tee with the baggy jeans and white sneakers.")
    result = suggest_outfit(SAMPLE_ITEM, SAMPLE_WARDROBE)
    assert isinstance(result, str)
    assert result.strip() != ""


def test_suggest_outfit_empty_wardrobe_does_not_crash(monkeypatch):
    _patch_groq(monkeypatch, "No wardrobe items available, but try jeans and sneakers.")
    result = suggest_outfit(SAMPLE_ITEM, {"items": []})
    assert isinstance(result, str)
    assert result.strip() != ""


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

FIT_CARD_ITEM = {
    "title": "Y2K Baby Tee — Butterfly Print",
    "price": 18.0,
    "platform": "depop",
    "colors": ["white", "pink", "purple"],
    "style_tags": ["y2k", "vintage", "graphic tee"],
}

SAMPLE_OUTFIT = "Pair the tee with baggy dark-wash jeans and chunky white sneakers."


def test_create_fit_card_normal_case(monkeypatch):
    _patch_groq(monkeypatch, "Just thrifted this Y2K baby tee on depop for $18 — obsessed!")
    result = create_fit_card(SAMPLE_OUTFIT, FIT_CARD_ITEM)
    assert isinstance(result, str)
    assert result.strip() != ""


def test_create_fit_card_empty_outfit_returns_error_string():
    # No mock needed: the guard should return before any LLM call.
    result = create_fit_card("", FIT_CARD_ITEM)
    assert isinstance(result, str)
    assert "no outfit" in result.lower()


# ── Failure modes (Milestone 5) ───────────────────────────────────────────────
# These deliberately trigger each tool's failure path and confirm graceful
# recovery — no exceptions, always a usable return value.

def test_search_listings_designer_ballgown_returns_empty():
    # Nothing in the dataset matches this query within the size/price limits.
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_suggest_outfit_empty_wardrobe_returns_fallback_on_api_failure(monkeypatch):
    # Even if the LLM call fails, an empty wardrobe must yield a usable string.
    _patch_groq_failure(monkeypatch)
    result = suggest_outfit(SAMPLE_ITEM, {"items": []})
    assert isinstance(result, str)
    assert result.strip() != ""


def test_create_fit_card_returns_error_string_on_api_failure(monkeypatch):
    # A failed LLM call should be caught and returned as a string, not raised.
    _patch_groq_failure(monkeypatch)
    result = create_fit_card(SAMPLE_OUTFIT, FIT_CARD_ITEM)
    assert isinstance(result, str)
    assert result.strip() != ""


# ── Tool 4: price_comparison (deterministic, no LLM) ──────────────────────────

def test_price_comparison_returns_useful_assessment():
    # Compare a real listing against the other "vintage denim" results.
    results = search_listings("vintage denim")
    assert len(results) > 1
    selected = results[0]
    result = price_comparison(selected, results)
    assert isinstance(result, str)
    text = result.lower()
    # Should reference the price comparison in some readable form.
    assert any(word in text for word in ("deal", "fair", "high", "$"))


def test_price_comparison_missing_price_returns_error():
    result = price_comparison({"title": "Mystery item"}, [{"price": 20.0}])
    assert result == "Price comparison not available: the selected item has no valid price."


def test_price_comparison_no_comparables_returns_fallback():
    # The only listing IS the selected item, so there is nothing to compare.
    item = {"id": "x1", "title": "Lonely Jacket", "price": 40.0, "category": "outerwear"}
    result = price_comparison(item, [item])
    assert isinstance(result, str)
    assert "not enough data" in result.lower()
