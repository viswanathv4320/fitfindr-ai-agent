"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import re

from tools import search_listings, suggest_outfit, create_fit_card, price_comparison


# ── query parsing ─────────────────────────────────────────────────────────────

# Filler words to drop from the description (the actual item keywords remain).
_FILLER = {
    "looking", "for", "a", "an", "the", "im", "i", "want", "need", "find",
    "me", "some", "something", "in", "size", "and", "to", "wear", "thats",
}


def _parse_query(query: str) -> dict:
    """
    Pull a description, size, and max_price out of a natural language query
    using simple regex/string rules (documented in planning.md).

    Returns a dict: {"description": str, "size": str | None, "max_price": float | None}
    """
    text = query.lower()

    # max_price: "under $30", "below 30", "max 25", or a bare "$30".
    price_match = re.search(r"(?:under|below|less than|max)\s*\$?\s*(\d+(?:\.\d+)?)", text)
    if not price_match:
        price_match = re.search(r"\$\s*(\d+(?:\.\d+)?)", text)
    max_price = float(price_match.group(1)) if price_match else None

    # size: "size M", a shoe size like "US 8.5", or a standalone XS/S/M/L/XL/XXL.
    size = None
    size_match = re.search(r"size\s+([a-z0-9./]+)", text)
    shoe_match = re.search(r"\bus\s*\d+(?:\.\d+)?\b", text)
    if size_match:
        size = size_match.group(1).upper()
    elif shoe_match:
        size = re.sub(r"\s+", " ", shoe_match.group(0).upper())
    else:
        standalone = re.search(r"\b(xxl|xl|xs|s|m|l)\b", text)
        if standalone:
            size = standalone.group(1).upper()

    # description: strip out the price/size phrases, then drop filler words.
    cleaned = re.sub(r"(?:under|below|less than|max)\s*\$?\s*\d+(?:\.\d+)?", " ", text)
    cleaned = re.sub(r"\$\s*\d+(?:\.\d+)?", " ", cleaned)
    cleaned = re.sub(r"size\s+[a-z0-9./]+", " ", cleaned)
    cleaned = re.sub(r"\bus\s*\d+(?:\.\d+)?\b", " ", cleaned)
    words = [w for w in re.findall(r"[a-z']+", cleaned) if w not in _FILLER]
    description = " ".join(words)

    return {"description": description, "size": size, "max_price": max_price}


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.

    You may add fields to this dict as needed for your implementation.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "price_assessment": None,    # string returned by price_comparison
        "error": None,               # set if the interaction ended early
        "retry_attempted": False,    # True if the search was retried with looser params
        "retry_params": None,        # the loosened params used on retry
        "retry_message": None,       # user-facing note about what was adjusted
        "style_profile": None,       # remembered style/color/budget preferences
        "style_memory_message": "",  # user-facing note when memory changed the search
        "search_description": "",    # description actually used for search (debug)
    }


def _reset_session(session: dict, query: str, wardrobe: dict) -> None:
    """
    Reset per-run state on an existing session in place, preserving the
    remembered style_profile so memory carries across queries.
    """
    preserved = session.get("style_profile")
    session.clear()
    session.update(_new_session(query, wardrobe))
    if preserved:
        session["style_profile"] = preserved


# ── style profile memory (stretch) ─────────────────────────────────────────────

_STYLE_KEYWORDS = [
    "vintage", "streetwear", "minimal", "minimalist", "grunge",
    "preppy", "casual", "classic", "boho", "sporty",
]
_COLOR_KEYWORDS = [
    "black", "white", "blue", "green", "red", "brown",
    "gray", "grey", "denim", "khaki", "cream",
]
# Specific garment words — if the query names one, keep the search focused on it
# instead of letting remembered style terms dominate.
_ITEM_WORDS = [
    "jacket", "hoodie", "tee", "shirt", "jeans", "shorts",
    "dress", "skirt", "sweater", "pants",
]


def update_style_profile(query: str, session: dict, max_price: float | None = None) -> dict:
    """
    Detect style/color preferences (and budget) in the query and remember them
    in session["style_profile"], avoiding duplicates.
    """
    profile = session.get("style_profile")
    if not profile:
        profile = {"preferred_styles": [], "preferred_colors": [], "budget_preference": None}
        session["style_profile"] = profile

    words = set(re.findall(r"[a-z]+", query.lower()))
    for kw in _STYLE_KEYWORDS:
        if kw in words and kw not in profile["preferred_styles"]:
            profile["preferred_styles"].append(kw)
    for kw in _COLOR_KEYWORDS:
        if kw in words and kw not in profile["preferred_colors"]:
            profile["preferred_colors"].append(kw)

    # Reuse the parsed price as the budget preference when one was given.
    if max_price is not None:
        profile["budget_preference"] = max_price

    return profile


def apply_style_memory(description: str, session: dict) -> str:
    """
    Append remembered styles/colors to the search description, but only the ones
    not already present. Sets a user-facing message when memory changed anything.
    Returns the (possibly unchanged) description.
    """
    profile = session.get("style_profile") or {}
    saved = profile.get("preferred_styles", []) + profile.get("preferred_colors", [])

    existing = set(re.findall(r"[a-z]+", description.lower()))

    # If the query names a specific item, don't let memory overpower it — keep
    # the search as-is and just note the remembered profile.
    if any(word in existing for word in _ITEM_WORDS):
        session["style_memory_message"] = (
            "Remembered style profile: " + ", ".join(saved) + "." if saved else ""
        )
        return description

    # Otherwise (vague query) fold in saved prefs not already mentioned.
    added = [word for word in saved if word not in existing]
    if not added:
        session["style_memory_message"] = ""
        return description

    new_description = f"{description} {' '.join(added)}".strip()
    session["style_memory_message"] = (
        "Using saved style preferences: " + ", ".join(added) + "."
    )
    return new_description


def _loosen_params(parsed: dict) -> dict:
    """
    Build looser search params for a retry, keeping the description the same.

    Loosening order (simple and deterministic):
      1. Drop the size filter if one was given.
      2. Otherwise, bump max_price by 25% if one was given.
      3. If neither size nor max_price was set, drop max_price entirely
         (no-op here, but keeps the description-only fallback explicit).
    """
    loosened = {
        "description": parsed["description"],
        "size": parsed["size"],
        "max_price": parsed["max_price"],
    }
    if parsed["size"] is not None:
        loosened["size"] = None
    elif parsed["max_price"] is not None:
        loosened["max_price"] = round(parsed["max_price"] * 1.25, 2)
    else:
        loosened["max_price"] = None
    return loosened


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict, session: dict | None = None) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.

    TODO — implement this function using the planning loop you designed in planning.md:

        Step 1: Initialize the session with _new_session().

        Step 2: Parse the user's query to extract a description, size, and
                max_price. You can use regex, string splitting, or ask the LLM
                to parse it — document your choice in planning.md.
                Store the result in session["parsed"].

        Step 3: Call search_listings() with the parsed parameters.
                Store results in session["search_results"].
                If no results: set session["error"] to a helpful message and
                return the session early. Do NOT proceed to suggest_outfit
                with empty input.

        Step 4: Select the item to use (e.g., the top result).
                Store it in session["selected_item"].

        Step 5: Call suggest_outfit() with the selected item and wardrobe.
                Store the result in session["outfit_suggestion"].

        Step 6: Call create_fit_card() with the outfit suggestion and selected item.
                Store the result in session["fit_card"].

        Step 7: Return the session.

    Before writing code, complete the Planning Loop and State Management sections
    of planning.md — your implementation should match what you described there.
    """
    # Step 1: get a session — reuse a passed-in one (so style memory persists),
    # otherwise start fresh. Either way, clear stale per-run state.
    if session is None:
        session = _new_session(query, wardrobe)
    else:
        _reset_session(session, query, wardrobe)

    # Reset the stale memory message each run (but keep style_profile).
    session["style_memory_message"] = ""

    # Step 2: parse the query into description / size / max_price.
    session["parsed"] = _parse_query(query)
    parsed = session["parsed"]

    # Step 2b (stretch): remember preferences, then fold saved ones into the
    # search description when they aren't already there.
    update_style_profile(query, session, parsed["max_price"])
    parsed["description"] = apply_style_memory(parsed["description"], session)
    session["search_description"] = parsed["description"]

    # Step 3: search listings with the parsed parameters.
    session["search_results"] = search_listings(
        parsed["description"], parsed["size"], parsed["max_price"]
    )

    # Step 3b (stretch): if nothing matched, retry once with looser constraints.
    if not session["search_results"]:
        session["retry_attempted"] = True
        retry = _loosen_params(parsed)
        session["retry_params"] = retry

        session["search_results"] = search_listings(
            retry["description"], retry["size"], retry["max_price"]
        )

        if session["search_results"]:
            # Explain to the user what we relaxed to find something.
            if parsed["size"] is not None and retry["size"] is None:
                adjusted = "removed the size filter"
            elif retry["max_price"] != parsed["max_price"]:
                adjusted = f"raised the price limit to ${retry['max_price']}"
            else:
                adjusted = "relaxed your filters"
            session["retry_message"] = (
                f"No exact matches, so we {adjusted} and found similar options."
            )

    # Still no results after the retry → record an error and stop.
    # Do NOT call suggest_outfit or create_fit_card.
    if not session["search_results"]:
        session["error"] = (
            "No products found that match your request, even after loosening the "
            "filters. Try a different description, size, or price."
        )
        return session

    # Step 4: select the top (best-scored) result.
    session["selected_item"] = session["search_results"][0]

    # Step 4b (stretch): deterministic price check against the other results.
    session["price_assessment"] = price_comparison(
        session["selected_item"], session["search_results"]
    )

    # Step 5: suggest an outfit using the selected item and the wardrobe.
    session["outfit_suggestion"] = suggest_outfit(
        session["selected_item"], session["wardrobe"]
    )

    # Step 6: turn the outfit + item into a shareable fit card.
    session["fit_card"] = create_fit_card(
        session["outfit_suggestion"], session["selected_item"]
    )

    # Step 7: return the completed session.
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
