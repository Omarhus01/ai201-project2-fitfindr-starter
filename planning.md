# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Foundational Decisions (cross-cutting)

These constrain every tool and the planning loop. Locked in Batch 1.

**D1 — Query parsing is LLM-based, lives in `agent.py` Step 2.** One Groq call turns the
raw user sentence into a structured JSON contract that Tool 1 and the loop consume:

```json
{ "description": str, "size": str | null, "max_price": float | null, "in_scope": bool }
```

- `description` — a CLEAN keyword phrase with the **head noun last** (e.g. `"vintage graphic tee"`,
  `"combat boots"`). The parser normalizes plurals/synonyms to the form that exists in the
  data (plural item nouns; `"tee"` not `"t-shirt"`).
- `size` — a **NORMALIZED, data-form size label**: `medium`→`M`, `size 8`→`US 8`,
  `30 waist`→`W30`, or `null` if no size was mentioned. The parser is the single
  normalization layer for size. Tool 1 does pure token-equality matching and carries no
  synonym/stem/word-map logic.
- `max_price` — float ceiling, or `null`.
- `in_scope` — `true` if the request is a thrift/styling query, `false` otherwise.

The parser prompt wording is locked in Batch 3. Because the parser now carries the full
precision of search, its Batch 3 verification must test normalization output (right head
noun, right size label), not just valid JSON — a silent mis-normalization surfaces as a
false no-results that the parse-failure guard below won't catch.

**D2 — Wardrobe source is whatever `run_agent` receives.** `app.py`'s radio passes
`get_example_wardrobe()` (normal path) or `get_empty_wardrobe()` (tests the empty-wardrobe
fallback in Tool 2). No change to the loaders.

**D3 — Return types (locked by the stubs):** `search_listings` → `list[dict]`,
`suggest_outfit` → `str`, `create_fit_card` → `str`.

**D4 — Session keys:** adopt `_new_session()` as-is. No-results, out-of-scope, and
parser-failure all use the existing `error` field + early return. No new keys.

**D5 — Input gate at the top of `run_agent`, driven by the parser's `in_scope` flag.**
If `in_scope` is `false` → set `error` to a brief, kind, on-topic-redirecting message and
return **before** `search_listings`. This is both the scope guard and a safety pre-filter:
clearly off-topic or distressing input is declined gently, never passed to the styling LLM.
Exact wording locked in Batch 3.

**Parser failure mode.** If the Groq parse call errors or returns non-JSON, the loop
catches it, sets `error` to a brief `"couldn't understand that — try naming an item, size,
or price"` message, and returns early — same shape as no-results and out-of-scope. The
agent never crashes and never passes garbage to `search_listings`. Wording locked in Batch 3.

**D6 — Data read discipline (no sanitization).** Listing titles are valid UTF-8 (the dash
is `U+2014` EM DASH, not corrupted bytes). All file reads use `encoding="utf-8"` —
`load_listings()` already does, so every consumer (Tool 1, Tools 2/3, `app.py`) receives
clean text. The `�` occasionally seen in Windows-terminal debug prints is a console
rendering artifact, not corrupted data, and does not appear in the Gradio UI. No
sanitization step is needed or wanted (a re-decode "repair" would corrupt the clean data).

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:** Filters the mock listings dataset to items matching the description
keywords, an optional size, and an optional price ceiling, ranked by keyword relevance.
Pure function over local JSON — no LLM, no network. Owns all size *matching* (but not
size *normalization* — see precondition).

**Precondition (contract):** `description` is a CLEAN keyword phrase with the head noun
last, and `size` is a NORMALIZED data-form label — both produced by the parser (D1). In
the real flow Tool 1 never sees raw user text, so messy inputs like `"combat boots in
black"` or `"jacket thats oversized"` are out-of-contract and won't reach it. Milestone 3
isolation tests therefore call Tool 1 with clean phrases (`"vintage graphic tee"`,
`"designer ballgown"`), not raw sentences.

**Input parameters:**
- `description` (str): clean keyword phrase, head noun last (e.g. `"vintage graphic tee"`,
  `"black combat boots"`). Drives relevance scoring. Colors live here as scored keywords —
  there is no color filter.
- `size` (str | None): normalized data-form size label (`"M"`, `"US 8"`, `"W30"`), or
  `None` to skip size filtering.
- `max_price` (float | None): inclusive price ceiling, or `None` to skip price filtering.

**What it returns:** `list[dict]` — matching listing dicts, each carrying all 11 original
fields (`id, title, description, category, style_tags, size, condition, price, colors,
brand, platform`), sorted by relevance descending. Empty list `[]` if nothing matches.
Never raises.

**Matching algorithm (apply in this exact order):**
1. Load via `load_listings()`.
2. **Hard filter — price:** keep if `max_price is None or listing["price"] <= max_price`.
3. **Hard filter — size:** if `None`, keep all. Else tokenize both the requested size and
   `listing["size"]` (split on `/`, whitespace, and parentheses → lowercased token set);
   keep if any requested token EQUALS a listing token, OR the listing is a `One Size`
   variant. Token-equality, never substring — so `8` matches `US 8` but not `US 8.5`, and
   `L` matches `L`/`L/XL`/`M/L` but not `XL` or `W30 L30`. No stemming: `boot` ≠ `boots`
   by design (the parser emits the data form).
4. **Relevance score:** lowercase + tokenize `description`, drop trivial stopwords; build
   the listing's combined text from `title + description + style_tags + category + colors`
   (joined, lowercased); score = count of distinct query tokens present.
5. **Head-noun gate:** drop any listing where the head noun (last description token after
   stopword removal) is absent from the combined text, even if score > 0. This is a
   deliberate precision-over-recall choice: it makes the no-results path fire honestly for
   items absent from the dataset (`"midi skirt"`, `"combat boots"`), at the cost of dropping
   a semantically-correct item whose text lacks the exact head word (e.g. a `"Bomber"` with
   no `"jacket"` in its text).
6. Drop score-0. Sort survivors by score desc, then `CONDITION_RANK` desc
   (`{"excellent": 3, "good": 2, "fair": 1}`), then price asc. Return.

**What happens if it fails or returns nothing:** returns `[]` (this includes the
empty-description case — a keyword-less search is not a real search). The planning loop
treats `[]` as the no-results branch: it sets `session["error"]` and does NOT call
`suggest_outfit`. Tool 1 itself never raises.

---

### Tool 2: suggest_outfit

**What it does:** Given a thrifted item and the user's wardrobe, asks the LLM
(`llama-3.3-70b-versatile` via the provided `_get_groq_client()`) to propose 1–2 complete
outfits built around the new item. Names real wardrobe pieces when the wardrobe is
non-empty; gives general styling advice when it's empty.

**Precondition:** `new_item` is a valid listing dict from `search_listings` — the planning
loop guarantees this. An empty wardrobe is a fallback path, **not** an error.

**Input parameters:**
- `new_item` (dict): a full listing dict. The prompt uses `title`, `category`, `colors`,
  `style_tags`, `condition`; `brand` is optional (`None` in 32/40 listings — never
  reference it if absent).
- `wardrobe` (dict): `{"items": [...]}` (the empty wardrobe also carries a `_note` key, so
  access it as `wardrobe.get("items", [])` — never assume the dict has only `items`). Each
  item has `id, name, category, colors, style_tags, notes` (`notes` may be `null`).

**What it returns:** a non-empty `str`.
- Non-empty wardrobe → references specific wardrobe pieces **by name**, as readable prose
  with light `Outfit 1: / Outfit 2:` labels at most (no bullets, no JSON).
- Empty wardrobe → general styling guidance (what categories/colors/vibes pair well)
  without inventing pieces the user doesn't own.

**Internal branch:**
- `wardrobe["items"]` empty → general-styling prompt.
- Non-empty → pass the **whole wardrobe** (10 items is small enough; let the LLM choose),
  including `name + category + colors + style_tags + notes` per item. The `notes` carry
  fit signal ("Really oversized — drops below the hip", "High-waisted") that makes
  suggestions specific. Ask for 1–2 outfits naming real pieces.

**Generation knobs:** model `llama-3.3-70b-versatile`; moderate temperature (coherence
matters more than novelty here — variability is Tool 3's job, not this one); optional
`max_tokens` ceiling to keep the suggestion concise, since the fit card consumes it next.

**What happens if it fails or returns nothing:**
- Empty wardrobe → handled by the fallback branch above (not an error).
- LLM returns empty/whitespace → return a safe non-empty fallback string ("Couldn't
  generate a styling idea for this one — try another item."), never `""`.
- LLM call raises (timeout/API error) → catch it, return a graceful fallback string, never
  propagate the exception.
- Item/wardrobe text is framed as descriptive data to style, never as instructions (the
  `in_scope` gate already filters off-topic input upstream).

---

### Tool 3: create_fit_card

**What it does:** Turns the outfit suggestion + the new item into a short, casual,
shareable caption — the kind of thing someone posts with an OOTD photo. Uses
`llama-3.3-70b-versatile` via the provided `_get_groq_client()`.

**Precondition:** in the live flow `outfit` is always non-empty, because `suggest_outfit`
returns a fallback string rather than `""`. The empty-`outfit` guard below therefore
exists for **Milestone 3 isolation tests and the Milestone 5 deliberate-failure trigger**
(`create_fit_card("", item)`), not the normal path — it is not dead code.

**Input parameters:**
- `outfit` (str): the suggestion string from `suggest_outfit`.
- `new_item` (dict): the listing dict. The caption mentions item `title`, `price`, and
  `platform` once each, naturally. `brand` may be `None` — never reference it if absent.

**What it returns:** a 2–4 sentence `str` caption that: feels authentic (not a product
description), mentions item name + price + platform once each, captures the outfit's vibe
in specific terms, and **varies across runs and inputs**.

**Formatting:** render price as `$22` (strip the trailing `.0`) and platform in casual
lowercase (`"depop"`), matching the reference voice ("thrifted this … off depop for $22 …").

**Generation knobs:** model `llama-3.3-70b-versatile`; temperature **0.9–1.0** and **no
fixed `seed`** (a fixed seed reproduces captions and fails the variability check regardless
of temperature); optional `max_tokens` ceiling to hold the 2–4 sentence target.

**What happens if it fails or returns nothing:**
- `outfit` empty/whitespace/missing → return a descriptive error **string** ("No outfit to
  caption yet — generate a styling idea first."); do **not** raise, do **not** call the LLM.
- LLM returns empty → return a safe fallback caption string, never `""`.
- LLM call raises → catch it, return a graceful fallback string, never propagate.
- `outfit`/item text is styled as content, never obeyed as instructions.

---

### Additional Tools (if any)

<!-- Copy the block above for any tools beyond the required three -->

---

## Planning Loop

**How does your agent decide which tool to call next?**
<!-- Describe the logic your planning loop uses. What does it look at? What conditions change its behavior? How does it know when it's done? -->

---

## State Management

**How does information from one tool get passed to the next?**
<!-- Describe how your agent stores and accesses state within a session. What data is tracked? How is it passed between tool calls? -->

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

<!-- Draw a diagram of your agent showing how the components connect:
     User input → Planning Loop → Tools (search_listings, suggest_outfit, create_fit_card)
                                                                          ↕
                                                                   State / Session
     Show what triggers each tool, how state flows between them, and where error paths branch off.
     ASCII art, a Mermaid diagram (https://mermaid.js.org/syntax/flowchart.html), or an embedded
     sketch are all fine. You'll share this diagram with an AI tool when asking it to implement
     the planning loop and each individual tool. -->

---

## AI Tool Plan

<!-- For each part of the implementation below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, your agent diagram)
     - What you expect it to produce
     - How you'll verify the output matches your spec before moving on

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Tool 1 spec (inputs, return value, failure mode) and ask it to implement
     search_listings() using load_listings() from the data loader — then test it against 3 queries
     before trusting it" is a plan. -->

**Milestone 3 — Individual tool implementations:**

**Milestone 4 — Planning loop and state management:**

---

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**What FitFindr does (overview):**
FitFindr takes a natural-language thrifting request and orchestrates three
tools in response to it. A user query triggers search_listings, which filters
the mock dataset by description, size, and price and returns matching items;
the top match flows into suggest_outfit, which uses the user's wardrobe to
propose how to wear it; that suggestion flows into create_fit_card, which
writes a short shareable caption. If search_listings finds nothing, the agent
tells the user what to adjust and stops — it does not call the later tools with
empty input.

**Things I saw in listings.json that I will need for Tool 1 spec:**
- Size labels are inconsistent across four families: letter (M, S/M, XL),
  "One Size"/oversized variants, waist (W30, W30 L30), and US shoe sizes (US 8).
  There are NO EU sizes and NO numeric body measurements — only labels.
- User queries use different vocabulary than the labels ("medium" -> "M",
  "size 8" -> "US 8"). Tool 1 must normalize the query to match the label,
  not the other way around.
- Decision: normalize obvious synonyms; treat size=None as "no filter";
  a size that simply isn't in the data (e.g. EU 45) is a legitimate no-results
  case -> error path, NOT a conversion to attempt.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:**
<!-- What does the agent do first? Which tool is called? With what input? -->

**Step 2:**
<!-- What happens next? What was returned from step 1? What tool is called now? -->

**Step 3:**
<!-- Continue until the full interaction is complete -->

**Final output to user:**
<!-- What does the user actually see at the end? -->
