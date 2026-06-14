# FitFindr

CodePath AI201 — Project 2

## Project Overview

FitFindr is a multi-tool AI agent for secondhand outfit search and styling. It searches listings, picks a matching item, suggests an outfit, creates a fit card, compares price, retries strict searches, and remembers simple style preferences.

## How to Run

```bash
pip install -r requirements.txt
python app.py
pytest
```

Create a `.env` file in the project root with your Groq key (free at [console.groq.com](https://console.groq.com)):

```
GROQ_API_KEY=your_key_here
```

## Dataset

`data/listings.json` has 40 mock listings (`id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, `platform`). `data/wardrobe_schema.json` defines the wardrobe format and includes an example wardrobe and an empty one. Load helpers live in `utils/data_loader.py`.

## Tool Inventory

1. **`search_listings(description: str, size: str | None, max_price: float | None)`**
   - Output: list of matching listings, or `[]`
   - Purpose: deterministic listing search
   - Error/fallback: returns an empty list if nothing matches

2. **`suggest_outfit(new_item: dict, wardrobe: list[dict])`**
   - Output: outfit suggestion string
   - Purpose: LLM-based styling suggestion
   - Error/fallback: handles an empty wardrobe and Groq failures safely

3. **`create_fit_card(outfit: str, new_item: dict)`**
   - Output: short fit card caption
   - Purpose: LLM-based caption generation
   - Error/fallback: returns a clear message if the outfit is empty

4. **`price_comparison(new_item: dict, listings: list[dict])`**
   - Output: price assessment string
   - Purpose: deterministic deal check against similar listings
   - Error/fallback: returns a clear message if the price is missing

## Planning Loop

`run_agent()` parses the query into description, size, and max price. It updates style memory, applies saved preferences only when helpful, searches listings, retries once if no result is found, selects the best item, generates an outfit, creates a fit card, compares price, and stores everything in the session for the UI.

Retry example: `vintage graphic tee size XS under $30` finds nothing at first, then retries without the size filter and returns a similar item.

## State Management

The app uses a session dictionary together with Gradio `gr.State({})`. Per-query outputs reset on each run, but `session["style_profile"]` persists for the rest of the browser session. Memory resets when the app restarts.

## Error Handling

- No exact result → retry removes the size filter.
- Empty wardrobe → general styling fallback.
- Empty outfit → fit card returns a clear message.
- Missing price → price comparison returns a clear message.
- Groq failure → safe fallback message instead of a crash.

## Stretch Features

1. **Retry Logic with Fallback** — if the first search is empty, retry once with looser constraints (drop size, then raise price).
2. **Price Comparison** — deterministic deal check comparing the picked item against similar listings.
3. **Style Profile Memory** — remembers styles, colors, and budget across queries.
   - Vague query like `find me anything` uses saved preferences.
   - Specific query like `find me a jacket` stays focused on jackets and just notes the saved profile.

## Testing

Tests live in `tests/test_tools.py` and `tests/test_agent.py`. LLM calls are mocked, so tests run offline without an API key. They cover search, size/price filters, retry, price comparison, empty wardrobe, fit card fallback, Groq failure, and style memory.

`pytest: all tests passing`

## AI Usage

**Example 1 — planning price comparison:** I used AI assistance to plan the price comparison stretch feature. I gave the AI my tool structure and expected output. It suggested where to call the tool and what tests to add. I kept the comparison deterministic instead of LLM-based.

**Example 2 — debugging style memory in Gradio:** I used AI assistance to debug Style Profile Memory. I gave screenshots showing memory was not persisting across submissions. The AI suggested using `gr.State({})`. I added session persistence and then adjusted the logic so memory would not override explicit item requests.

## Spec Reflection

- **What worked well:** the fixed planning loop kept tools simple to build and test one at a time, and the session dict made state easy to follow.
- **What was challenging:** persisting style memory across Gradio submissions, and tuning memory so it didn't overpower specific item searches.
- **Limitation:** keyword search is simple and can miss semantic matches (e.g. synonyms).
- **Future improvement:** use embeddings or better ranking for smarter, more relevant matches.
