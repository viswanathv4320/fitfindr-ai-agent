"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    # Load every listing from the dataset.
    listings = load_listings()

    # Turn the description into lowercase query terms, dropping stopwords.
    stopwords = {"a", "the", "for", "under", "with"}
    terms = [w for w in description.lower().split() if w and w not in stopwords]
    if not terms:
        return []

    # Normalize the requested size into a token for strict matching.
    wanted_size = size.strip().upper() if size else None

    # How many points each field is worth when a term is found in it.
    field_weights = {
        "title": 3,
        "colors": 2,
        "style_tags": 2,
        "category": 2,
        "description": 1,
        "brand": 1,
    }

    results = []
    for listing in listings:
        # --- Hard filter: price ---
        if max_price is not None and listing.get("price", 0) > max_price:
            continue

        # --- Hard filter: size ---
        # Sizes can be compound like "S/M" or "W30 L30", so split into tokens
        # (on "/" and spaces). size="M" matches "M", "S/M", "M/L" but not "S".
        if wanted_size is not None:
            tokens = listing.get("size", "").upper().replace("/", " ").split()
            if wanted_size not in tokens:
                continue

        # Build the searchable text for each field (lists joined into a string).
        fields = {
            "title": listing.get("title", ""),
            "colors": " ".join(listing.get("colors", [])),
            "style_tags": " ".join(listing.get("style_tags", [])),
            "category": listing.get("category", ""),
            "description": listing.get("description", ""),
            "brand": listing.get("brand") or "",
        }
        fields = {name: text.lower() for name, text in fields.items()}

        # Score the listing: add each field's weight for every term it contains,
        # and remember which terms matched anywhere.
        match_score = 0
        matched_terms = []
        for term in terms:
            term_matched = False
            for name, text in fields.items():
                if term in text:
                    match_score += field_weights[name]
                    term_matched = True
            if term_matched:
                matched_terms.append(term)

        # Require at least 60% of the query terms to match.
        if len(matched_terms) < 0.6 * len(terms):
            continue

        # Attach debug fields without mutating the original listing.
        results.append({**listing, "match_score": match_score, "matched_terms": matched_terms})

    # Sort by highest score first, then lowest price, and keep the top 5.
    results.sort(key=lambda item: (-item["match_score"], item["price"]))
    return results[:5]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    # Describe the new item for the prompt.
    item_desc = (
        f"{new_item.get('title', 'an item')} "
        f"(category: {new_item.get('category', 'unknown')}, "
        f"colors: {', '.join(new_item.get('colors', [])) or 'n/a'}, "
        f"style: {', '.join(new_item.get('style_tags', [])) or 'n/a'})"
    )

    # Safely pull the wardrobe items list, handling missing/malformed input.
    items = []
    if isinstance(wardrobe, dict):
        items = wardrobe.get("items") or []

    if items:
        # Format each wardrobe piece into a readable line for the prompt.
        wardrobe_lines = "\n".join(
            f"- {it.get('name', 'item')} "
            f"({it.get('category', '?')}; {', '.join(it.get('colors', [])) or 'n/a'})"
            for it in items
        )
        prompt = (
            f"The user is considering buying this thrifted item:\n{item_desc}\n\n"
            f"Here is what they already own:\n{wardrobe_lines}\n\n"
            "Suggest 1-2 complete outfits that pair the new item with specific "
            "pieces from their wardrobe. Name the wardrobe pieces you use and "
            "briefly explain why each outfit works. Only use the new item and the "
            "wardrobe pieces listed above. Keep it concise and natural."
        )
    else:
        # Fallback when there is no wardrobe to work with.
        prompt = (
            f"The user is considering buying this thrifted item:\n{item_desc}\n\n"
            "They did not provide any wardrobe items. Start your answer by noting "
            "that no wardrobe items were available, then suggest 1-2 outfits using "
            "common wardrobe basics (e.g. plain tees, jeans, sneakers) that would "
            "style this item well. Keep it concise, natural, and practical."
        )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful, down-to-earth fashion stylist.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        # Never crash the agent flow — return a usable fallback tip.
        if items:
            return (
                f"Style your {new_item.get('title', 'new piece')} with your "
                "favorite jeans and a clean pair of sneakers for an easy everyday look."
            )
        return (
            "No wardrobe items were available. Pair your "
            f"{new_item.get('title', 'new piece')} with wardrobe basics like a plain "
            "tee, well-fitting jeans, and simple sneakers for a versatile look."
        )


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    # Guard against a missing or whitespace-only outfit.
    if not outfit or not outfit.strip():
        return "Could not create a fit card: no outfit suggestion was provided."

    # Pull item details with safe defaults for any missing fields.
    title = new_item.get("title") or "unknown item"
    price = new_item.get("price")
    price_str = f"${price}" if price is not None else "unknown price"
    platform = new_item.get("platform") or "unknown platform"
    colors = ", ".join(new_item.get("colors", [])) or "n/a"
    style_tags = ", ".join(new_item.get("style_tags", [])) or "n/a"

    prompt = (
        "Write a short, shareable OOTD-style caption (2-4 sentences) for this thrifted find.\n\n"
        f"Item: {title}\n"
        f"Price: {price_str}\n"
        f"Platform: {platform}\n"
        f"Colors: {colors}\n"
        f"Style tags: {style_tags}\n"
        f"Outfit: {outfit}\n\n"
        "Guidelines:\n"
        "- Sound casual and authentic, like a real person posting their fit (not a product listing).\n"
        "- Mention the item name, the price, and the platform naturally, once each.\n"
        "- Capture the outfit's vibe in specific terms.\n"
        "Return only the caption."
    )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": "You write fun, authentic outfit captions for social media.",
                },
                {"role": "user", "content": prompt},
            ],
            # Higher than suggest_outfit so captions vary between runs.
            temperature=1.0,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Could not create a fit card right now: {e}"
    

# ── Tool 4: price_comparison ───────────────────────────────────────────────────
def price_comparison(new_item: dict, listings: list) -> str:
    """
    Compare the selected thrifted item against comparable listings and return
    a short price assessment with reasoning.

    Args:
        new_item: The selected listing dict for the thrifted item.
        listings: A list of listing dictionaries to compare against.

    Returns:
        A short string explaining whether the selected item looks like a good deal,
        fair price, or overpriced based on comparable listings.

        If there are not enough comparable listings or price data is missing,
        return a descriptive message string — do NOT raise an exception.

    The assessment should:
    - Compare the selected item's price to similar listings
    - Use category, style tags, colors, brand, and condition when available
    - Mention the selected price, average comparable price, and number of comparable items
    - Explain the reasoning in plain language
    - Avoid using an LLM; this should be a deterministic tool

    TODO:
        1. Validate that new_item has a usable price.
        2. Find comparable listings from the provided listings list.
        3. Exclude the selected item itself from comparisons.
        4. Compute average comparable price.
        5. Return a clear price assessment string.
        6. Handle missing/empty comparison data gracefully.
    """
    def _price(item):
        """Return the item's price as a float, or None if it isn't numeric."""
        p = item.get("price") if isinstance(item, dict) else None
        return float(p) if isinstance(p, (int, float)) else None

    # --- Validate the selected item and its price ---
    if not isinstance(new_item, dict) or _price(new_item) is None:
        return "Price comparison not available: the selected item has no valid price."

    if not listings:
        return "Price comparison not available: no listings to compare against."

    title = new_item.get("title", "this item")
    item_price = _price(new_item)
    item_id = new_item.get("id")

    # --- Find comparable listings (exclude the item itself, need a price) ---
    others = []
    for lst in listings:
        if not isinstance(lst, dict) or _price(lst) is None:
            continue
        if item_id is not None and lst.get("id") == item_id:
            continue
        others.append(lst)

    if not others:
        return f"Not enough data to compare the price of {title}."

    # Prefer same-category listings; fall back to all others if none share it.
    category = new_item.get("category")
    comparables = [lst for lst in others if lst.get("category") == category] or others

    # Optionally narrow to ones that also share a style tag, color, brand, or
    # condition — but only if that leaves us something to compare against.
    item_tags = set(new_item.get("style_tags", []))
    item_colors = set(new_item.get("colors", []))
    item_brand = new_item.get("brand")
    item_condition = new_item.get("condition")

    def _is_similar(lst):
        return (
            item_tags & set(lst.get("style_tags", []))
            or item_colors & set(lst.get("colors", []))
            or (item_brand and lst.get("brand") == item_brand)
            or (item_condition and lst.get("condition") == item_condition)
        )

    similar = [lst for lst in comparables if _is_similar(lst)]
    if similar:
        comparables = similar

    # --- Compute the comparison stats ---
    prices = [_price(lst) for lst in comparables]
    avg = sum(prices) / len(prices)
    low, high = min(prices), max(prices)
    count = len(prices)

    # --- Classify against a +/- 15% band around the average ---
    if item_price <= avg * 0.85:
        verdict = "a good deal — priced below similar items"
    elif item_price <= avg * 1.15:
        verdict = "a fair price — in line with similar items"
    else:
        verdict = "on the high side — priced above similar items"

    return (
        f"{title} is ${item_price:.2f}. Compared to {count} similar listing(s) "
        f"averaging ${avg:.2f} (range ${low:.2f}–${high:.2f}), it looks like {verdict}."
    )


if __name__ == "__main__":
    def show(description, size=None, max_price=None):
        results = search_listings(description, size, max_price)
        print(f"\nQuery: '{description}' | size={size} | max=${max_price}")
        print(f"Found {len(results)} results")
        for item in results:
            print(
                f"- {item['title']} | size={item['size']} | ${item['price']} "
                f"| score={item['match_score']} | matched={item['matched_terms']}"
            )

    show("black denim jacket", size="M", max_price=50)
    show("vintage denim", size=None, max_price=None)

    # ── Tool 2: suggest_outfit ──
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    sample_item = {
        "title": "Y2K Baby Tee — Butterfly Print",
        "category": "tops",
        "colors": ["white", "pink", "purple"],
        "style_tags": ["y2k", "vintage", "graphic tee"],
    }

    print("\n--- suggest_outfit: normal wardrobe ---")
    print(suggest_outfit(sample_item, get_example_wardrobe()))

    print("\n--- suggest_outfit: empty wardrobe ---")
    print(suggest_outfit(sample_item, get_empty_wardrobe()))

    # ── Tool 3: create_fit_card ──
    sample_outfit = (
        "Pair the butterfly baby tee with baggy dark-wash jeans and chunky white "
        "sneakers for a playful Y2K everyday look."
    )
    fit_card_item = {
        "title": "Y2K Baby Tee — Butterfly Print",
        "price": 18.0,
        "platform": "depop",
        "colors": ["white", "pink", "purple"],
        "style_tags": ["y2k", "vintage", "graphic tee"],
    }

    print("\n--- create_fit_card: normal case ---")
    print(create_fit_card(sample_outfit, fit_card_item))

    print("\n--- create_fit_card: empty outfit ---")
    print(create_fit_card("", fit_card_item))

    # ── Tool 4: price_comparison ──
    denim_results = search_listings("vintage denim", size=None, max_price=None)
    if denim_results:
        selected = denim_results[0]
        print("\n--- price_comparison: normal case ---")
        print(price_comparison(selected, denim_results))

    print("\n--- price_comparison: failure case ---")
    print(price_comparison({}, []))