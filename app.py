"""
app.py

Gradio interface for FitFindr. The layout and wiring are already set up —
your job is to fill in handle_query() so it calls run_agent() and maps
the session results to the three output panels.

Run with:
    python app.py

Then open the localhost URL shown in your terminal (usually http://localhost:7860,
but check your terminal — the port may differ).
"""

import gradio as gr

from agent import run_agent
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── query handler ─────────────────────────────────────────────────────────────

def handle_query(
    user_query: str, wardrobe_choice: str, session: dict | None
) -> tuple[str, str, str, str, dict]:
    """
    Called by Gradio when the user submits a query.

    Args:
        user_query:     The text the user typed into the search box.
        wardrobe_choice: Either "Example wardrobe" or "Empty wardrobe (new user)".
        session:         The persisted session dict (from gr.State), kept across
                         submissions so style memory accumulates.

    Returns:
        A tuple of four panel strings plus the updated session dict:
            (listing_text, outfit_suggestion, fit_card, price_assessment, session)
    """
    # Carry the session across submissions so style_profile persists.
    if session is None:
        session = {}

    # 1. Guard against an empty query.
    if not user_query or not user_query.strip():
        return "Please enter what you're looking for.", "", "", "", session

    # 2. Pick the wardrobe based on the radio choice.
    if wardrobe_choice == "Empty wardrobe (new user)":
        wardrobe = get_empty_wardrobe()
    else:
        wardrobe = get_example_wardrobe()

    # 3. Run the agent (the app never calls the tools directly).
    #    Passing the session lets run_agent reset per-run fields while keeping
    #    session["style_profile"] from previous searches. Capture the return so
    #    we hand gr.State back exactly what the agent produced.
    session = run_agent(user_query, wardrobe, session)

    # 4. Error / no-results path.
    if session.get("error"):
        return (
            session["error"],
            "No outfit yet — try another search above.",
            "No fit card yet — find a piece first!",
            "No price comparison available.",
            session,
        )

    # 5. Success path — format the selected listing into a readable block.
    item = session.get("selected_item") or {}
    lines = []
    # If saved style preferences shaped this search, note that first.
    if session.get("style_memory_message"):
        lines.append(f"Style memory:\n{session['style_memory_message']}\n")
    # If the search was loosened, note that above the listing.
    if session.get("retry_message"):
        lines.append(f"Note: {session['retry_message']}\n")
    lines.append(f"Top listing:\n{item.get('title', 'Untitled listing')}")
    if item.get("price") is not None:
        lines.append(f"Price: ${item['price']}")
    if item.get("size"):
        lines.append(f"Size: {item['size']}")
    if item.get("platform"):
        lines.append(f"Platform: {item['platform']}")
    if item.get("condition"):
        lines.append(f"Condition: {item['condition']}")
    listing_text = "\n".join(lines)

    # Fall back to friendly placeholders if a tool returned nothing.
    outfit = session.get("outfit_suggestion") or "No outfit suggestion available."
    fit_card = session.get("fit_card") or "No fit card available."
    price_assessment = session.get("price_assessment") or "No price comparison available."

    return listing_text, outfit, fit_card, price_assessment, session


# ── interface ─────────────────────────────────────────────────────────────────

EXAMPLE_QUERIES = [
    "vintage graphic tee under $30",
    "90s track jacket in size M",
    "flowy midi skirt under $40",
    "black combat boots size 8",
    "designer ballgown size XXS under $5",   # deliberate no-results test
]

def build_interface():
    with gr.Blocks(title="FitFindr") as demo:
        gr.Markdown("""
# FitFindr 🛍️
Find secondhand pieces and get outfit ideas based on your wardrobe.
Describe what you're looking for — include size and price if you want to filter.
        """)

        with gr.Row():
            query_input = gr.Textbox(
                label="What are you looking for?",
                placeholder="e.g. vintage graphic tee under $30, size M",
                lines=2,
                scale=3,
            )
            wardrobe_choice = gr.Radio(
                choices=["Example wardrobe", "Empty wardrobe (new user)"],
                value="Example wardrobe",
                label="Wardrobe",
                scale=1,
            )

        submit_btn = gr.Button("Find it", variant="primary")

        # Persists the session dict across submissions so style memory builds up.
        session_state = gr.State({})

        with gr.Row():
            listing_output = gr.Textbox(
                label="🛍️ Top listing found",
                lines=8,
                interactive=False,
            )
            outfit_output = gr.Textbox(
                label="👗 Outfit idea",
                lines=8,
                interactive=False,
            )
            fitcard_output = gr.Textbox(
                label="✨ Your fit card",
                lines=8,
                interactive=False,
            )
            price_output = gr.Textbox(
                label="💰 Price check",
                lines=8,
                interactive=False,
            )

        gr.Examples(
            examples=[[q, "Example wardrobe"] for q in EXAMPLE_QUERIES],
            inputs=[query_input, wardrobe_choice],
            label="Try these queries",
        )

        submit_btn.click(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice, session_state],
            outputs=[listing_output, outfit_output, fitcard_output, price_output, session_state],
        )
        query_input.submit(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice, session_state],
            outputs=[listing_output, outfit_output, fitcard_output, price_output, session_state],
        )

    return demo


if __name__ == "__main__":
    demo = build_interface()
    demo.launch()
