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
from tools import _format_price
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe
from utils.profile import load_profile, save_profile


# ── query handler ─────────────────────────────────────────────────────────────

def handle_query(user_query: str, wardrobe_choice: str, style_note: str = "") -> tuple[str, str, str]:
    """
    Called by Gradio when the user submits a query.

    Args:
        user_query:     The text the user typed into the search box.
        wardrobe_choice: Either "Example wardrobe" or "Empty wardrobe (new user)".
        style_note:      Optional free-text style preference (Stretch 4), threaded
                          into suggest_outfit's prompt when non-empty.

    Returns:
        A tuple of three strings:
            (listing_text, outfit_suggestion, fit_card)
        Each string maps to one of the three output panels in the UI.

    TODO:
        1. Guard against an empty query (return early with an error message).
        2. Select the wardrobe based on wardrobe_choice.
        3. Call run_agent() with the query and selected wardrobe.
        4. If session["error"] is set, return the error in the first panel
           and empty strings for the other two.
        5. Otherwise, format session["selected_item"] into a readable listing_text
           string and return it along with session["outfit_suggestion"] and
           session["fit_card"].
    """
    # 1. Empty-query guard (this guard lives here, not in the loop).
    if not user_query or not user_query.strip():
        return "Please enter what you're looking for.", "", ""

    # 2. Select the wardrobe from the radio choice.
    wardrobe = (
        get_example_wardrobe()
        if wardrobe_choice == "Example wardrobe"
        else get_empty_wardrobe()
    )

    # 3. Run the agent.
    session = run_agent(user_query, wardrobe, style_note.strip() or None)

    # 4. Error path: show the message in panel 1, leave the others empty.
    if session["error"]:
        return session["error"], "", ""

    # 5. Success: format the top listing for panel 1 (factual display — platform as-is).
    item = session["selected_item"]
    listing_text = (
        f"{item['title']} — {_format_price(item['price'])}, "
        f"{item['platform']}, {item['condition']} condition"
    )
    # Stretch 1: tell the user when the size filter was dropped to find this result.
    if session.get("loosened"):
        listing_text = "No exact size match — showing results without the size filter.\n" + listing_text

    # Stretch 2: append the price-check line, but only when there's enough data to back it.
    price_check = session.get("price_check")
    if price_check and price_check["verdict"] != "insufficient data":
        listing_text += (
            f"\nPrice check: {price_check['verdict']} "
            f"({_format_price(price_check['item_price'])} vs "
            f"{_format_price(price_check['median_comparable'])} median for {item['category']})"
        )

    return listing_text, session["outfit_suggestion"], session["fit_card"]


# ── interface ─────────────────────────────────────────────────────────────────

EXAMPLE_QUERIES = [
    "vintage graphic tee under $30",
    "90s track jacket in size M",
    "flowy midi skirt under $40",
    "black combat boots size 8",
    "designer ballgown size XXS under $5",   # deliberate no-results test
]

def build_interface():
    # Stretch 4: load any saved profile once at build time to prefill the UI.
    # A fresh clone has no file yet, so this is None and the UI just shows its defaults.
    saved_profile = load_profile()
    initial_wardrobe = (saved_profile or {}).get("wardrobe_choice", "Example wardrobe")
    initial_note = (saved_profile or {}).get("style_note", "")

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
                value=initial_wardrobe,
                label="Wardrobe",
                scale=1,
            )

        with gr.Row():
            style_note_input = gr.Textbox(
                label="Style note (optional)",
                placeholder="e.g. I like y2k and grunge",
                value=initial_note,
                lines=1,
                scale=3,
            )
            save_profile_btn = gr.Button("Save my style profile", scale=1)

        save_status = gr.Markdown(visible=False)

        submit_btn = gr.Button("Find it", variant="primary")

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

        gr.Examples(
            examples=[[q, "Example wardrobe"] for q in EXAMPLE_QUERIES],
            inputs=[query_input, wardrobe_choice],
            label="Try these queries",
        )

        submit_btn.click(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice, style_note_input],
            outputs=[listing_output, outfit_output, fitcard_output],
        )
        query_input.submit(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice, style_note_input],
            outputs=[listing_output, outfit_output, fitcard_output],
        )
        save_profile_btn.click(
            fn=lambda wc, note: (
                save_profile({"wardrobe_choice": wc, "style_note": note}),
                gr.Markdown(value="Saved.", visible=True),
            )[1],
            inputs=[wardrobe_choice, style_note_input],
            outputs=[save_status],
        )

    return demo


if __name__ == "__main__":
    demo = build_interface()
    demo.launch()
