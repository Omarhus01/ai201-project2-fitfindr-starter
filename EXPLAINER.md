# FitFindr — How Everything Works

This is just for you. Plain language, no jargon. If something still doesn't
make sense after reading, that's on the explanation not on you.

---

## 1. What Does This Project Actually Do?

You type something like `"vintage graphic tee under $30, size M"` and the
agent figures out what to buy, how to wear it, and gives you a caption to post.

Three steps, three answers. That's it.

```mermaid
flowchart TD
    A["User types a sentence"] --> B["Query Parser\n(LLM call 1)\nturns messy text into clean JSON"]
    B --> C["search_listings\n(pure Python, no LLM)\nfinds matching items in the dataset"]
    C --> D["suggest_outfit\n(LLM call 2)\ngenerates outfit ideas"]
    D --> E["create_fit_card\n(LLM call 3)\nwrites a shareable caption"]
    E --> F["Three panels appear in the UI"]
```

---

## 2. The Files and What They Do

Think of this like a kitchen. The tools are the knives and pans. The agent is
the chef who decides what to use and when. The app is the restaurant that
shows the food to the customer.

```mermaid
flowchart LR
    subgraph UI["app.py — the restaurant"]
        A["User clicks Find it"]
    end

    subgraph Loop["agent.py — the chef"]
        B["run_agent()\ndecides which tools to call"]
    end

    subgraph Tools["tools.py — the kitchen tools"]
        C["search_listings"]
        D["suggest_outfit"]
        E["create_fit_card"]
        F["compare_price"]
    end

    subgraph Data["utils/ — the pantry"]
        G["data_loader.py\nreads JSON files"]
        H["profile.py\nsaves/loads style preferences"]
    end

    A --> B
    B --> C
    B --> D
    B --> E
    B --> F
    C --> G
    A --> H
```

One rule to remember: `tools.py` has no idea that `agent.py` or `app.py` exist.
It's just a collection of functions you can call from anywhere. That's why you
can test each tool on its own without running the whole app.

---

## 3. The Session Dict — The Shared Notepad

This is the most important concept in the whole project so read this carefully.

When a user submits a query, `run_agent()` creates one Python dictionary called
`session`. Every single step of the agent reads from it and writes back into it.
It's the shared memory for the whole interaction.

```mermaid
flowchart LR
    S["session dict\nthe shared notepad"]

    S -->|"reads"| T1["search_listings"]
    T1 -->|"writes search_results\nand selected_item"| S

    S -->|"reads selected_item\nand wardrobe"| T2["suggest_outfit"]
    T2 -->|"writes outfit_suggestion"| S

    S -->|"reads outfit_suggestion\nand selected_item"| T3["create_fit_card"]
    T3 -->|"writes fit_card"| S

    S -->|"app.py reads\nthese three fields"| UI["Panel 1\nPanel 2\nPanel 3"]
```

Here is what the session looks like at the end of a successful run:

```python
session = {
    "query":             "vintage graphic tee under $30",
    "parsed":            {"description": "vintage graphic tee",
                          "size": None,
                          "max_price": 30.0,
                          "in_scope": True},
    "search_results":    [ ...list of matching listings... ],
    "selected_item":     { ...the top listing... },   # this is results[0]
    "wardrobe":          { ...the user's wardrobe... },
    "outfit_suggestion": "Pair it with your baggy jeans and combat boots...",
    "fit_card":          "just thrifted this faded tee for $18...",
    "error":             None,       # None means everything worked
    "loosened":          None,       # explained in Stretch 1 section
    "price_check":       {"verdict": "good deal", ...},
}
```

`session["error"]` is the most important field. If it's `None`, everything worked.
If it's a string, something failed and `app.py` shows that string in Panel 1
instead of a listing.

---

## 4. The Planning Loop — What Actually Runs

`run_agent()` is NOT just "call all three tools one by one no matter what."
It checks the result of each step and either continues or stops early with an error.

```mermaid
flowchart TD
    Start["run_agent() called"] --> P["call _parse_query()"]

    P -->|"ValueError\nbad JSON from LLM"| E1["error: 'I couldn't read that request'\nRETURN"]
    P -->|"any other Exception\nAPI is down"| E2["error: 'service trouble'\nRETURN"]
    P -->|"in_scope is False\noff-topic query"| E3["error: 'FitFindr only helps with clothing'\nRETURN"]
    P -->|"parsed ok"| Search["call search_listings()"]

    Search -->|"returns empty list"| SizeCheck{"was a size\nfilter applied?"}
    SizeCheck -->|"yes"| Retry["RETRY without size filter\nStretch 1"]
    Retry -->|"still empty"| E4["error: 'No listings matched...'\nRETURN"]
    Retry -->|"found results"| SetLoosened["set session loosened\ncontinue with these results"]
    SizeCheck -->|"no"| E5["error: 'No listings matched...'\nRETURN"]

    Search -->|"found results"| Pick["selected_item = results 0"]
    SetLoosened --> Pick

    Pick --> Price["compare_price()\nStretch 2, never blocks"]
    Price --> Outfit["suggest_outfit()"]
    Outfit --> Card["create_fit_card()"]
    Card --> Done["RETURN session\nerror is None"]
```

The three early exits at the top are why the agent never crashes or calls tools
with bad input. If search returns nothing, `suggest_outfit` never gets called.
Period.

---

## 5. How search_listings Finds Things

This one has no LLM. It's pure Python filtering over a local JSON file.
Here's the logic for `"vintage graphic tee"`, size `"M"`, max price `$30`:

```mermaid
flowchart TD
    Load["load all listings from listings.json"] --> ForEach["for each listing..."]

    ForEach --> PriceCheck{"price > 30?"}
    PriceCheck -->|"yes"| Skip1["SKIP"]
    PriceCheck -->|"no"| SizeCheck{"size filter?\ncheck subset rule"}

    SizeCheck -->|"doesn't match"| Skip2["SKIP"]
    SizeCheck -->|"matches or no filter"| Score["calculate relevance score\ncount how many query words\nappear in the listing text"]

    Score --> HeadNoun{"does 'tee' appear\nin the listing text?"}
    HeadNoun -->|"no"| Skip3["SKIP\nhead noun gate"]
    HeadNoun -->|"yes"| Keep["KEEP this listing\nwith its score"]

    Keep --> Sort["sort all kept listings\nby score DESC\nthen condition DESC\nthen price ASC"]
    Sort --> Return["return sorted list"]
```

**The subset rule for sizes:** this is a subtle thing that matters.

The user wants size `"M"`. That gets turned into the token set `{"m"}`.
A listing sized `"S/M"` becomes `{"s", "m"}`.
Is `{"m"}` a subset of `{"s", "m"}`? Yes. So it matches.

But for shoes: user wants `"US 8"` which becomes `{"us", "8"}`.
A listing sized `"US 8.5"` becomes `{"us", "8.5"}`.
Is `{"us", "8"}` a subset of `{"us", "8.5"}`? No, because `"8" != "8.5"`. Correct.

If the rule was "any token matches" instead of "all tokens must match", then
`"US 8"` would match `"US 8.5"` because they both have `"us"`. That's wrong.

**The head noun:** the last word of the description after removing stopwords.
`"vintage graphic tee"` has head noun `"tee"`.
A listing must contain the word `"tee"` or it gets rejected entirely even if
its score is high. This stops a "vintage" boots listing from showing up.

---

## 6. How suggest_outfit Works

This tool has two completely different modes depending on whether you have
wardrobe items or not.

```mermaid
flowchart TD
    Call["suggest_outfit(new_item, wardrobe, style_note)"] --> Check{"wardrobe items list\nis empty?"}

    Check -->|"YES"| PathA["PATH A — General advice\nDo NOT invent pieces\nJust say what kinds of things\npair well with this item"]
    Check -->|"NO"| PathB["PATH B — Specific outfits\nFormat all wardrobe items\nAsk LLM to name specific pieces\nthe user actually owns"]

    PathA --> LLM1["LLM call\ntemperature 0.7"]
    PathB --> LLM2["LLM call\ntemperature 0.7"]

    LLM1 -->|"API fails or returns empty"| Fallback["return safe fallback string\nnever crashes"]
    LLM2 -->|"API fails or returns empty"| Fallback
    LLM1 -->|"success"| Return["return the suggestion string"]
    LLM2 -->|"success"| Return
```

Temperature 0.7 means "moderately creative." The LLM gives different answers
each run but stays on-topic. It won't start talking about pizza.

---

## 7. How create_fit_card Works

Takes the outfit string and the listing, writes a casual caption.
The most important thing here is the empty-outfit guard at the top.

```mermaid
flowchart TD
    Call["create_fit_card(outfit, new_item)"] --> Guard{"outfit string\nis empty?"}

    Guard -->|"YES"| EarlyReturn["return 'No outfit to caption yet'\nno LLM call at all"]
    Guard -->|"NO"| Build["build the prompt\nitem name + price + platform + outfit"]

    Build --> LLM["LLM call\ntemperature 0.95\nhigh randomness = different each time"]

    LLM -->|"API fails or returns empty"| Fallback["return safe fallback string"]
    LLM -->|"success"| Return["return the caption string"]
```

Temperature 0.95 is much higher than the outfit tool. That's on purpose.
The fit card should sound fresh and different every time you run it. Lower
temperature would make every caption start sounding the same.

---

## 8. The Query Parser — Why It Exists

Users type messy sentences. Tools need clean structured data. The parser is
the translator between those two worlds. It's an LLM call that always returns
valid JSON because we use Groq's "JSON mode."

```mermaid
flowchart LR
    Raw["User: 'I want a tee shirt,\nmedium, nothing over 30 bucks'"]
    -->|"LLM call\ntemperature 0.0\njson mode ON"| Parsed["Parsed JSON:\ndescription: 'tees'\nsize: 'M'\nmax_price: 30.0\nin_scope: true"]
    --> Tools["search_listings gets\nclean structured data\nnot a messy sentence"]
```

`in_scope` is the off-topic filter. If someone asks "what's the weather?" the
parser returns `in_scope: false` and the agent politely declines before wasting
any API calls on styling tools.

Temperature 0.0 means fully deterministic. The parser should always give the
same output for the same input. We don't want creative parsing.

---

## 9. compare_price — The Price Check

Compares the item's price against the median price of all other listings
in the same category.

```mermaid
flowchart TD
    Start["compare_price(item)"] --> Check{"is item a valid dict\nwith price and category?"}
    Check -->|"no"| Insuf1["return 'insufficient data'"]
    Check -->|"yes"| Load["load all listings\nfind others in same category\nexclude this item by id"]

    Load --> Count{"at least 2\ncomparables?"}
    Count -->|"no"| Insuf2["return 'insufficient data'"]
    Count -->|"yes"| Median["calculate median price\nof comparables"]

    Median --> Pct["pct = (item_price - median) / median"]
    Pct --> Verdict{"pct vs threshold 15%"}
    Verdict -->|"pct is less than -15%"| GoodDeal["verdict: 'good deal'"]
    Verdict -->|"pct is more than +15%"| High["verdict: 'high'"]
    Verdict -->|"in between"| Fair["verdict: 'fair'"]
```

Why median and not average? Say one listing in "tops" is a $500 designer piece.
That would drag the average way up and make everything look like a good deal.
Median ignores outliers. It just gives you the middle value.

This tool never blocks the flow. Even if it returns "insufficient data", the
agent keeps going and generates the outfit suggestion anyway.

---

## 10. How Gradio Connects Python to the Browser

Gradio builds a web page for you from pure Python. No HTML, no JavaScript.
You just define inputs and outputs and wire a function to a button.

```mermaid
flowchart TD
    Click["User clicks Find it"] --> Gradio["Gradio calls handle_query()\nwith the three input values"]

    Gradio --> HQ["handle_query(\n  user_query,\n  wardrobe_choice,\n  style_note\n)"]

    HQ --> Agent["calls run_agent()\ngets back session dict"]

    Agent -->|"session error is set"| ShowError["return error string to Panel 1\nempty string to Panel 2 and 3"]
    Agent -->|"session error is None"| Format["format listing text\nadd price check line if available\nadd loosened warning if needed"]

    Format --> Return["return\n(listing_text, outfit_suggestion, fit_card)"]

    ShowError --> P1["Panel 1 shows error"]
    Return --> P1b["Panel 1 shows listing"]
    Return --> P2["Panel 2 shows outfit"]
    Return --> P3["Panel 3 shows fit card"]
```

When you return a tuple of three strings from `handle_query()`, Gradio knows
to put the first string in Panel 1, second in Panel 2, third in Panel 3.
That wiring is set up at the bottom of `app.py` with `.click()`.

---

## 11. Error Handling — Every Way Things Can Break

```mermaid
flowchart TD
    Q["User submits query"] --> E1{"empty query?"}
    E1 -->|"yes"| R1["'Please enter what you are looking for'"]
    E1 -->|"no"| E2{"parser fails?\nbad JSON"}
    E2 -->|"yes"| R2["'I couldn't read that request'"]
    E2 -->|"no"| E3{"API is down?"}
    E3 -->|"yes"| R3["'service trouble, try again'"]
    E3 -->|"no"| E4{"off-topic query?"}
    E4 -->|"yes"| R4["'FitFindr only helps with clothing'"]
    E4 -->|"no"| E5{"no results found?"}
    E5 -->|"yes, had size filter"| Retry["retry without size\nStretch 1"]
    Retry -->|"still nothing"| R5["'No listings matched... try adjusting'"]
    Retry -->|"found results"| Happy
    E5 -->|"yes, no size filter"| R6["'No listings matched... try adjusting'"]
    E5 -->|"no"| Happy["happy path\nall three panels fill up"]
```

Nothing crashes. Every failure returns a helpful message that tells the user
what went wrong and what to try instead.

---

## 12. How Tests Work Without Calling the API

Every test in this project runs fully offline. No Groq API key needed.
The trick is called monkeypatching.

`_chat()` in `tools.py` is the one function that actually calls Groq.
In tests, we swap it out for a fake function that just returns a hardcoded string.

```mermaid
flowchart LR
    Test["test calls suggest_outfit()"] --> Tool["suggest_outfit() calls _chat()"]
    Tool -->|"in production"| Real["real _chat()\ncalls Groq API\nneeds internet + key"]
    Tool -->|"in tests\nmonkeypatched"| Fake["fake _chat()\nreturns 'Wear it with jeans.'\ninstantly, no network"]
```

```python
# How monkeypatching looks in a test:
def test_suggest_outfit_returns_string(monkeypatch):
    monkeypatch.setattr(tools, "_chat", lambda *args, **kwargs: "Wear it with jeans.")
    result = suggest_outfit(some_item, some_wardrobe)
    assert isinstance(result, str)
    assert result == "Wear it with jeans."
```

`monkeypatch.setattr(tools, "_chat", fake_function)` temporarily replaces
the real `_chat` with the fake one just for that one test. After the test
finishes, it automatically gets put back. Clean, isolated, fast.

This is why `_chat` was kept as a thin, dumb wrapper with no extra logic inside
it. The simpler the function, the easier it is to replace in tests.

---

## 13. The Stretch Features

```mermaid
flowchart LR
    S1["Stretch 1\nRetry logic"]
    S2["Stretch 2\nPrice comparison"]
    S4["Stretch 4\nStyle profile memory"]

    S1 --> A1["Lives in agent.py\nBranch 2a\nIf size filter causes no results,\nautomatically retry without it"]
    S2 --> A2["Lives in tools.py compare_price\nand agent.py Step 3 and app.py Panel 1\nCompares item vs category median\nshows good deal / fair / high"]
    S4 --> A3["Lives in utils/profile.py and app.py\nSaves wardrobe choice and style note\nto data/style_profile.json\nPrefills UI next time you open the app"]
```

---

## 14. One Full Run From Start to Finish

Query: `"vintage graphic tee under $30"`, Example wardrobe, style note `"I like y2k"`

```mermaid
sequenceDiagram
    participant User
    participant app as app.py
    participant agent as agent.py
    participant tools as tools.py
    participant groq as Groq API
    participant data as listings.json

    User->>app: clicks Find it
    app->>agent: run_agent("vintage graphic tee under $30", wardrobe, "I like y2k")
    agent->>groq: _parse_query() — LLM call 1
    groq-->>agent: {"description":"vintage graphic tee","size":null,"max_price":30.0,"in_scope":true}
    agent->>tools: search_listings("vintage graphic tee", None, 30.0)
    tools->>data: load_listings()
    data-->>tools: all 50 listings
    tools-->>agent: [Y2K Baby Tee $18, Faded Band Tee $22, ...]
    agent->>tools: compare_price(Y2K Baby Tee)
    tools->>data: load_listings() again for comparables
    data-->>tools: all listings
    tools-->>agent: {"verdict":"good deal","item_price":18,"median_comparable":21.5}
    agent->>groq: suggest_outfit(Y2K Baby Tee, wardrobe, "I like y2k") — LLM call 2
    groq-->>agent: "Outfit 1: Pair with Baggy straight-leg jeans and Black combat boots..."
    agent->>groq: create_fit_card(outfit, Y2K Baby Tee) — LLM call 3
    groq-->>agent: "I'm obsessing over this Y2K Baby Tee I scored for $18 on depop..."
    agent-->>app: session dict with all results
    app-->>User: Panel 1: listing + price check\nPanel 2: outfit suggestion\nPanel 3: fit card
```

Total LLM calls per run: 3 (parser + outfit + fit card).
`search_listings` and `compare_price` are pure Python — no LLM calls.

---

That's everything. If you re-read sections 3, 4, and 5 you'll understand 80%
of how the project works. The rest is just details on top of those three ideas.
