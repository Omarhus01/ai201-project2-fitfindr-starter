"""
app.py

The Gradio web interface for FitFindr.

WHAT THIS FILE DOES:
  - Builds the UI (text inputs, radio buttons, output panels, example queries)
  - Defines handle_query(), which bridges the UI and the agent loop
  - Launches the app on a local web server

WHAT THIS FILE DOES NOT DO:
  - It does not implement any tools or agent logic — all of that lives in
    tools.py and agent.py. This file just calls run_agent() and displays results.

GRADIO BASICS (if this is your first time seeing it):
  Gradio lets you build a web UI in pure Python with no HTML/CSS/JavaScript.
  You define input components (Textbox, Radio) and output components (Textbox),
  then wire a Python function to a button click. Gradio handles the rest.
  `gr.Blocks` is the layout system — with gr.Row() you place things side by side.
"""

import gradio as gr

from agent import run_agent
from tools import _format_price           # used to format the price in Panel 1
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe
from utils.profile import load_profile, save_profile   # Stretch 4


# ─────────────────────────────────────────────────────────────────────────────
# QUERY HANDLER — the bridge between the UI and the agent
# ─────────────────────────────────────────────────────────────────────────────

def handle_query(user_query: str, wardrobe_choice: str, style_note: str = "") -> tuple[str, str, str]:
    """
    Called by Gradio every time the user clicks "Find it" or presses Enter.

    This function's job is simple:
      1. Validate the input (non-empty query)
      2. Convert the wardrobe_choice radio string → actual wardrobe dict
      3. Call run_agent() to do all the real work
      4. Map the session dict → three strings for the three output panels

    Args:
        user_query:      The text the user typed in the search box.
        wardrobe_choice: The radio button value — either "Example wardrobe"
                         or "Empty wardrobe (new user)". This is a string,
                         not a dict — we convert it to the actual wardrobe here.
        style_note:      Optional style preference from the style note box
                         (Stretch 4). Empty string if the user left it blank.

    Returns:
        A tuple of three strings: (listing_text, outfit_suggestion, fit_card)
        Gradio automatically puts these into the three output Textbox panels
        in the order they're listed in the .click() wiring at the bottom.
    """
    # 1. Guard against empty input. The UI could technically send an empty
    #    string (e.g. user clicks Find it without typing anything).
    if not user_query or not user_query.strip():
        return "Please enter what you're looking for.", "", ""

    # 2. Convert the radio button string → the actual wardrobe dict.
    #    get_example_wardrobe() returns ~10 real wardrobe items.
    #    get_empty_wardrobe() returns {"items": []}.
    wardrobe = (
        get_example_wardrobe()
        if wardrobe_choice == "Example wardrobe"
        else get_empty_wardrobe()
    )

    # 3. Run the agent. This is where all the real work happens — parsing,
    #    searching, outfit suggestion, fit card. Returns a session dict.
    #    style_note.strip() converts "  " → ""; `or None` converts "" → None.
    session = run_agent(user_query, wardrobe, style_note.strip() or None)

    # 4a. Error path: something went wrong (no results, parse failure, etc.)
    #     Put the error message in Panel 1, leave the other two empty.
    #     Returning three strings is what Gradio expects — one per output component.
    if session["error"]:
        return session["error"], "", ""

    # 4b. Success path: format the top listing for Panel 1.
    item = session["selected_item"]
    listing_text = (
        f"{item['title']} — {_format_price(item['price'])}, "
        f"{item['platform']}, {item['condition']} condition"
    )

    # Stretch 1: if the agent had to drop the size filter to find results,
    # prepend a note so the user knows this isn't an exact size match.
    if session.get("loosened"):
        listing_text = "No exact size match — showing results without the size filter.\n" + listing_text

    # Stretch 2: if the price check returned a meaningful verdict
    # (i.e., not "insufficient data"), append it to the listing text.
    # "insufficient data" means there weren't enough comparable listings to judge.
    price_check = session.get("price_check")
    if price_check and price_check["verdict"] != "insufficient data":
        listing_text += (
            f"\nPrice check: {price_check['verdict']} "
            f"({_format_price(price_check['item_price'])} vs "
            f"{_format_price(price_check['median_comparable'])} median for {item['category']})"
        )

    # Return all three panel strings. Gradio maps them positionally:
    # first string → listing_output, second → outfit_output, third → fitcard_output.
    return listing_text, session["outfit_suggestion"], session["fit_card"]


# ─────────────────────────────────────────────────────────────────────────────
# INTERFACE DEFINITION
# ─────────────────────────────────────────────────────────────────────────────

# These are the pre-filled example queries in the "Try these queries" section.
# The last one is deliberately impossible — it's the no-results test case.
EXAMPLE_QUERIES = [
    "vintage graphic tee under $30",
    "90s track jacket in size M",
    "flowy midi skirt under $40",
    "black combat boots size 8",
    "designer ballgown size XXS under $5",   # deliberate no-results test
]


def build_interface():
    """
    Build and return the Gradio Blocks interface.

    Called once at startup. Returns a `demo` object that we call .launch() on.

    STRETCH 4 — PROFILE PREFILL:
    At build time, we try to load the saved style profile from disk.
    If one exists, we use its wardrobe_choice and style_note as the initial
    values for those UI components. If no profile exists yet, the UI just
    shows its hardcoded defaults. This runs once, at startup — not on every query.
    """
    # Try to load a saved profile. Returns None if no file exists yet.
    saved_profile = load_profile()
    # Use the saved values if they exist, otherwise fall back to defaults.
    initial_wardrobe = (saved_profile or {}).get("wardrobe_choice", "Example wardrobe")
    initial_note = (saved_profile or {}).get("style_note", "")

    # gr.Blocks() is the Gradio layout container. Everything defined inside
    # the `with` block becomes part of the page.
    with gr.Blocks(title="FitFindr") as demo:

        # Header markdown — shown at the top of the page.
        gr.Markdown("""
# FitFindr 🛍️
Find secondhand pieces and get outfit ideas based on your wardrobe.
Describe what you're looking for — include size and price if you want to filter.
        """)

        # Row 1: search box (wide) + wardrobe choice (narrow)
        with gr.Row():
            query_input = gr.Textbox(
                label="What are you looking for?",
                placeholder="e.g. vintage graphic tee under $30, size M",
                lines=2,
                scale=3,    # takes up 3/4 of the row width
            )
            wardrobe_choice = gr.Radio(
                choices=["Example wardrobe", "Empty wardrobe (new user)"],
                value=initial_wardrobe,   # prefilled from saved profile if available
                label="Wardrobe",
                scale=1,    # takes up 1/4 of the row width
            )

        # Row 2: style note box (wide) + save profile button (narrow)
        with gr.Row():
            style_note_input = gr.Textbox(
                label="Style note (optional)",
                placeholder="e.g. I like y2k and grunge",
                value=initial_note,       # prefilled from saved profile if available
                lines=1,
                scale=3,
            )
            save_profile_btn = gr.Button("Save my style profile", scale=1)

        # Hidden status line that appears briefly after saving.
        save_status = gr.Markdown(visible=False)

        # The main submit button.
        submit_btn = gr.Button("Find it", variant="primary")

        # Row 3: three output panels side by side.
        with gr.Row():
            listing_output = gr.Textbox(
                label="🛍️ Top listing found",
                lines=8,
                interactive=False,   # read-only — user can't type into output panels
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

        # Pre-filled example queries that users can click to auto-fill the search box.
        gr.Examples(
            examples=[[q, "Example wardrobe"] for q in EXAMPLE_QUERIES],
            inputs=[query_input, wardrobe_choice],
            label="Try these queries",
        )

        # ── Event wiring ──────────────────────────────────────────────────────
        # These lines connect UI events (button clicks, Enter key) to Python functions.

        # Clicking "Find it" → calls handle_query with the three inputs,
        # puts the three returned strings into the three output panels.
        submit_btn.click(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice, style_note_input],
            outputs=[listing_output, outfit_output, fitcard_output],
        )

        # Pressing Enter in the query box does the same thing as clicking "Find it".
        query_input.submit(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice, style_note_input],
            outputs=[listing_output, outfit_output, fitcard_output],
        )

        # Clicking "Save my style profile" → calls save_profile() via a lambda,
        # then shows the "Saved." status message.
        # The lambda takes two inputs (wardrobe choice and style note) and
        # returns a Markdown component update that makes the status visible.
        save_profile_btn.click(
            fn=lambda wc, note: (
                save_profile({"wardrobe_choice": wc, "style_note": note}),
                gr.Markdown(value="Saved.", visible=True),
            )[1],   # [1] picks the second item from the tuple — the Markdown update
            inputs=[wardrobe_choice, style_note_input],
            outputs=[save_status],
        )

    return demo


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # build_interface() constructs the Gradio layout.
    # .launch() starts the local web server and opens the browser.
    # The URL is printed to the terminal — usually http://localhost:7860
    # but Gradio picks a different port if 7860 is already in use.
    demo = build_interface()
    demo.launch()
