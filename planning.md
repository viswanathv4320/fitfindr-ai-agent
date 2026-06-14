# FitFindr — planning.md

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Search the thrift listings in `data/listings.json` for products that match the user’s requested item description, size, and budget.

**Input parameters:**
- `description` (str): the keywords describing the desired clothing item (e.g. “vintage graphic tee”, “90s track jacket”).
- `size` (str): the requested size, such as S, M, L, XL, XS, shoe sizes like US 7 or US 8.5, or a range like S/M.
- `max_price` (float): the maximum price the user is willing to pay.

**What it returns:**
A list of matching listing dictionaries, each containing all product fields from `listings.json` such as `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, and `platform`.

**What happens if it fails or returns nothing:**
If no matching listings are found, the agent should stop the flow and return a friendly error message such as “No products found that match your request.” This prevents the agent from moving on to outfit suggestion or fit card creation with no item selected.

---

### Tool 2: suggest_outfit

**What it does:**
Use the selected thrift listing and the user’s wardrobe to generate 1–2 outfit ideas that pair the new item with existing pieces.

**Input parameters:**
- `new_item` (dict): the selected listing dictionary from 
- `wardrobe` (dict): the user’s wardrobe dict with an `items` list from `wardrobe_schema.json`.

**What it returns:**
A string describing one or two outfit combinations, naming wardrobe pieces and explaining how they work with the new item.

**What happens if it fails or returns nothing:**
If the wardrobe is empty, return general styling advice for the selected item instead of a full outfit. If no outfit can be generated, return a fallback styling tip so the agent still has something useful to show.

---

### Tool 3: create_fit_card

**What it does:**
Turn the outfit recommendation and the selected thrift item into a short caption-style fit card the user can read or share.

**Input parameters:**
- `outfit` (str): the outfit suggestion text from `suggest_outfit`.
- `new_item` (dict): the selected listing dictionary, including `title`, `price`, and `platform`.

**What it returns:**
A 2–4 sentence caption that mentions the item, price, platform, and overall vibe of the outfit.

**What happens if it fails or returns nothing:**
If the outfit string is missing or empty, return a safe fallback caption or note instead of crashing. If item details are incomplete, use the available fields and still produce a readable message.

---

### Additional Tools (if any)

### Tool 4: price_comparison

**What it does:**
Compare the selected thrift listing’s price to similar items in `data/listings.json` and return a price assessment with reasoning.

**Input parameters:**
- `new_item` (dict): the selected listing dictionary from `search_listings`.
- `listings` (list[dict]): the full dataset of available thrift listings to compare against.

**What it returns:**
A string with a price assessment and reasoning, for example whether the item is priced fairly, expensive, or a good deal compared to comparable items.

**What happens if it fails or returns nothing:**
If there are no comparable listings or the comparison cannot be made, return a safe fallback message such as “Price comparison not available for this item.” and do not prevent the other tools from running if the rest of the flow still makes sense.

---

## Planning Loop

**How does your agent decide which tool to call next?**
The planning loop follows a fixed sequence with explicit condition checks at each stage.

1. Parse the user query into `description`, `size`, and `max_price`.
2. Call `search_listings(description, size, max_price)`.
   - If `search_results` is empty, set `session["error"]` to a friendly message and return early.
   - If `search_results` is not empty, set `session["selected_item"] = search_results[0]`.
3. Call `suggest_outfit(session["selected_item"], session["wardrobe"])`.
   - If `wardrobe["items"]` is empty, `suggest_outfit` should return general styling advice instead of a full outfit.
   - Store the returned string in `session["outfit_suggestion"]`.
4. Call `create_fit_card(session["outfit_suggestion"], session["selected_item"])`.
   - If `outfit` is missing or empty, create a safe fallback caption rather than raising an exception.
   - Store the result in `session["fit_card"]`.
5. Return the session dict with `selected_item`, `outfit_suggestion`, and `fit_card` populated unless an error occurred.

The loop is done once the final fit card has been created or an error has been recorded.

---

## State Management

**How does information from one tool get passed to the next?**

The agent keeps one `session` dict for the whole run. Every tool reads what it needs from this dict and writes its result back, so the next tool can pick it up. Nothing is passed through global variables — the session dict is the single source of truth.

State after each step:
- **After parsing the query:** `session` holds `description`, `size`, `max_price`, and the loaded `wardrobe`.
- **After `search_listings`:** `session["search_results"]` holds the list of matches, and `session["selected_item"]` holds the top match. If nothing matched, `session["error"]` is set instead.
- **After `suggest_outfit`:** `session["outfit_suggestion"]` holds the outfit text. It reads `selected_item` and `wardrobe` from the session.
- **After `create_fit_card`:** `session["fit_card"]` holds the caption. It reads `outfit_suggestion` and `selected_item` from the session.
- **After `price_comparison`:** `session["price_assessment"]` holds the price reasoning. It reads `selected_item` and the full listings from the session.

At the end, the full `session` dict is returned so the user can see the selected item, outfit, fit card, and price together.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | |
| suggest_outfit | Wardrobe is empty | |
| create_fit_card | Outfit input is missing or incomplete | |

---

## Architecture

User Input (query + wardrobe_choice)
         │
         ▼
   Parse Query
   • Extract: description, size, max_price
   • Load wardrobe
         │
         ▼
Session State ◀─ Store parsed params
         │
         ▼
search_listings(description, size, max_price)
   INPUT: description, size, max_price
   OUTPUT: list of matching items
         │
         ├─ NO RESULTS ─────────┐
         │                      │
         │                      ▼
         │              ❌ Set session["error"]
         │              Return Early
         │
         ├─ HAS RESULTS
         │
         ▼
Session State ◀─ Store search_results, selected_item
         │
         ▼
suggest_outfit(new_item, wardrobe)
   INPUT: selected_item, wardrobe
   OUTPUT: outfit suggestion string
         │
         ▼
Session State ◀─ Store outfit_suggestion
         │
         ▼
create_fit_card(outfit, new_item)
   INPUT: outfit_suggestion, selected_item
   OUTPUT: fit card caption string
         │
         ▼
Session State ◀─ Store fit_card
         │
         ▼
price_comparison(new_item, listings)
   INPUT: selected_item, all listings
   OUTPUT: price assessment string
         │
         ▼
Session State ◀─ Store price_assessment
         │
         ▼
Return Complete Session Dict to User
         │
         ▼
Display: Listing + Outfit + Caption + Price

---

## AI Tool Plan

**Milestone 3 — Individual tool implementations:**
I'll use Claude my Tool 1 inputs, return value and failure as mentioned in this planning.md file
and ask it to implement search_listings() using load_listings() from the data loader.

I'll use Claude my Tool 2 inputs, return value and failure as mentioned in this planning.md file
and ask it to implement suggest_outfit() using the Groq API with new_item and wardrobe.

I'll use Claude my Tool 3 inputs, return value and failure as mentioned in this planning.md file
and ask it to implement create_fit_card() using the Groq API with outfit and new_item.

I'll use Claude my Tool 4 inputs, return value and failure as mentioned in this planning.md file
and ask it to implement price_comparison() by comparing new_item price with similar items in listings.

**Milestone 4 — Planning loop and state management:**
I'll organize the agent loop in agent.py to follow the fixed sequence. Initialize a session dict and parse the user query into description, size, and max_price. Call search_listings and check if results are empty. If empty, set session["error"] and return early. If results exist, store search_results and selected_item in session. Then call suggest_outfit with selected_item and wardrobe, storing outfit_suggestion in session. Then call create_fit_card with outfit_suggestion and selected_item, storing fit_card in session. Finally call price_comparison with selected_item and all listings, storing price_assessment in session. Return the complete session dict with all results to the user.

---

## A Complete Interaction (Step by Step)

FitFindr is a multi-tool AI agent that helps a user find secondhand clothing items and decide how to style them. The user can describe what they are looking for in natural language so that the agent understands the request, decides which tools are needed, call them in the right order and return the final recommendation.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:**
Purpose: Search for secondhand clothing listings based on the user's request.
Triggered When: The user asks to find, search, compare or recommend a clothing item.
Inputs: description, size, max_price
Output: A list of matching items
Failure Handling: If it returns no result, the agent should stop the plan. Give out a friendly error message.

**Step 2:**
What happens next: take the top matching item from the search results and call the outfit tool with it and the user’s wardrobe.
Triggered When: search_listings returns at least one item.
Inputs: new_item, wardrobe
Output: A styled outfit recommendation string
Failure Handling: If the wardrobe is empty, return a general styling tip instead of a specific outfit.

**Step 3:**
What happens next: take the outfit recommendation and the selected item, then call the fit card tool.
Triggered When: suggest_outfit returns a non-empty result.
Inputs: outfit, new_item
Output: A short caption-style fit card with item details, price, platform, and vibe.
Failure Handling: If outfit text is missing, return a safe fallback caption rather than crashing.

**Final output to user:**
The user sees the top thrift listing found, a styled outfit recommendation for that listing, and a short fit card caption they can use to describe or share the look.
