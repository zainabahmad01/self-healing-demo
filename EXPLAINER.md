# Self-Healing Locators — Explained From Scratch

This repo is **Playwright for Python** driven by **pytest** (`pytest-playwright`).
The Python files are the source of truth.

<!--
  Previous TypeScript / Playwright-test version of this explainer is preserved
  in HTML comments below each section (do not delete).
-->

## 1. The problem this solves

When you write an automated UI test, you tell it *where* to click/type using a
"locator" — a rule that finds an element on the page. For example:

```py
page.locator("#username").fill("tomsmith")
```

<!--
```ts
page.locator('#username').fill('tomsmith');
```
-->

`#username` means "find the element with id=`username`". This works fine — until a
developer changes the page and renames that id to something else, like
`user-login-input`. Now your test can't find the element anymore and fails, even
though the login form still works perfectly fine for a real human user.

Normally someone has to notice the failure, open the test, find the new id, and
fix the locator by hand. Do this across hundreds of tests and it becomes a
part-time job just keeping locators up to date.

**Self-healing** is the idea of automating that fix: when a locator breaks, before
failing the test, ask an AI "hey, here's the page's HTML, and here's what I was
originally looking for — where did it go?" The AI reads the HTML and suggests a
new locator. The test tries that, and if it works, the test continues instead of
failing.

The healed locator is **not** written back into the test file. It lives in memory
for that run, and a line is appended to `logs/self-heal-audit.jsonl` as a paper
trail. The next `pytest` still starts from the original (broken) selector.

## 2. The building blocks (the tech)

| Piece | What it is | Why it's here |
|---|---|---|
| **Playwright for Python** | A browser automation framework (drives real Chrome/Chromium, clicks buttons, fills forms, etc.) | It's what actually runs the test and controls the browser |
| **pytest + pytest-playwright** | Test runner and the `page` fixture | Collects tests, launches Chromium, injects `page` |
| **Python** | The language this repo is written in | Adapted from a TypeScript source; this checkout is Python |
| **Ollama** | A program that runs AI language models *on your own machine* (no internet, no API key, no cost per call) | This is the "local AI model" — instead of paying OpenAI per request, we run a smaller model locally |
| **llama3.2:3b** | A small open-source language model (3 billion parameters) that Ollama runs | This is the actual "brain" that reads the page HTML and guesses a new locator |
| **A target website** | `the-internet.herokuapp.com/login` — a public demo login page | Something simple to test against — a username field, a password field, a submit button |

<!--
| Piece | What it is | Why it's here |
|---|---|---|
| **Playwright** | A browser automation framework (drives real Chrome/Chromium, clicks buttons, fills forms, etc.) | It's what actually runs the test and controls the browser |
| **TypeScript** | JavaScript with types | The whole project is written in it, matches the source repo this was adapted from |
| **Ollama** | A program that runs AI language models *on your own machine* (no internet, no API key, no cost per call) | This is the "local AI model" — instead of paying OpenAI per request, we run a smaller model locally |
| **llama3.2:3b** | A small open-source language model (3 billion parameters) that Ollama runs | This is the actual "brain" that reads the page HTML and guesses a new locator |
| **A target website** | `the-internet.herokuapp.com/login` — a public demo login page | Something simple to test against — a username field, a password field, a submit button |
-->

Nothing here needs an API key or costs money. Everything happens on your laptop.
(Optional cloud path: set `"provider": "openai"` in `utils/LLMs/llm-config.json`
and `OPENAI_API_KEY` in the environment.)

The model does **not** click or type. Playwright does every browser action. The
LLM only reads a sanitized HTML snippet and returns candidate locators as JSON.

## 3. The moving parts in this repo

```
self-healing-demo/
├── conftest.py                          ← puts project root on sys.path
├── pytest.ini                           ← Chromium + traces on failure
├── tests/
│   └── test_self_healing_login.py       ← the actual test (start here)
├── utils/models/
│   ├── llm_config.py                    ← TypedDict for llm-config.json
│   └── ai_response_model.py             ← TypedDict for the LLM JSON shape
├── utils/LLMs/
│   ├── self_healing_locator.py          ← the "brain" that decides when/how to heal
│   ├── llm_client.py                    ← talks to Ollama (the AI)
│   ├── locator_helper.py                ← figures out what *kind* of locator broke (id? css? text?)
│   ├── llm-config.json                  ← settings: which model, which URL, etc.
│   └── self_heal_audit_log.py           ← writes a log line every time healing succeeds
└── logs/self-heal-audit.jsonl           ← created after your first run; a history of every heal
```

<!--
```
self-healing-demo/
├── tests/
│   └── self-healing-login.spec.ts   ← the actual test (start here)
├── utils/LLMs/
│   ├── SelfHealingLocator.ts        ← the "brain" that decides when/how to heal
│   ├── LLMClient.ts                 ← talks to Ollama (the AI)
│   ├── LocatorHelper.ts             ← figures out what *kind* of locator broke (id? css? text?)
│   ├── llm-config.json              ← settings: which model, which URL, etc.
│   └── selfHealAuditLog.ts          ← writes a log line every time healing succeeds
└── logs/self-heal-audit.jsonl       ← created after your first run; a history of every heal
```
-->

## 4. Step by step: what actually happens when you run the test

1. **pytest starts Chromium (via pytest-playwright) and the test goes to the login page.**
   (`page.goto("https://the-internet.herokuapp.com/login")`)

2. **The test uses a locator that is deliberately wrong on purpose**, to simulate
   what happens in real life when a developer renames something:
   ```py
   broken_username_selector = "#username_field_renamed"  # wrong! real id is #username
   ```

   <!--
   ```ts
   const brokenUsernameSelector = '#username_field_renamed'; // wrong! real id is #username
   ```
   -->

3. **`SelfHealingLocator.find_element()` tries that locator first**, just like a
   normal test would — it waits up to 10 seconds for `#username_field_renamed` to
   appear on the page (`wait_for(state="attached")`).

   <!--
   3. **`SelfHealingLocator.findElement()` tries that locator first**, just like a
      normal test would — it waits up to 10 seconds for `#username_field_renamed` to
      appear on the page.
   -->

4. **It doesn't exist, so this fails.** Instead of throwing an error immediately
   (like a normal test), the healer moves to the next step.

5. **It checks for any "backup" locators it may have found before** (there are
   none yet on the first attempt), then decides it's time to call the AI.

6. **It grabs the page's HTML** — cleaned up first (scripts, styles, SVGs, and other
   noise stripped out, and capped at 60,000 chars) so the AI isn't overwhelmed. This
   happens in `_get_html_for_healing()` via `page.evaluate(...)`. Prefer a
   `[role="dialog"]` if one exists, else `document.body`.

   <!--
   6. **It grabs the page's HTML** — cleaned up first (scripts, styles, and other
      noise stripped out, and capped in size) so the AI isn't overwhelmed. This
      happens in `getHtmlForHealing()`.
   -->

7. **It builds a prompt and sends it to Ollama**, which is running locally on
   `http://127.0.0.1:11434/api/generate`. The prompt basically says:
   > "I was looking for something with id=`username_field_renamed`. Here's the
   > page's HTML. What are some robust ways to find the element I actually
   > meant?"

8. **Ollama runs the `llama3.2:3b` model** on your machine's CPU/GPU and returns
   an answer. This is the "AI thinking" step, and it's why the test is marked
   `@pytest.mark.timeout(120)`. It responds with structured JSON, e.g.:
   ```json
   {
     "id": null,
     "name": "username",
     "xpath": "//input[@name='username']",
     "css": "input[name='username']",
     "link_text": "Username"
   }
   ```

9. **The healer turns each of those suggestions into a real Playwright locator**
   (e.g. `name: "username"` becomes the selector `[name="username"]`) and stores
   them all as backup strategies on `self.locator_strategies` (in memory only).

10. **It retries** — first the original (still broken) locator, then each backup
    in turn (2s wait each). The first one that actually finds an attached element
    **wins**.

11. **That healed locator is returned to the test**, which then goes right on
    filling in the username, password, and clicking Login — exactly as if
    nothing had gone wrong. Password and submit still use ordinary
    `page.locator(...)` (not healed).

12. **A line gets appended to `logs/self-heal-audit.jsonl`** recording what broke
    and what it got healed to, so you have a paper trail. `.jsonl` means JSON
    Lines (one JSON object per line), so each heal is appended without rewriting
    the whole file. Nothing reads this file on the next run.
    ```json
    {"ts":"...","brokenPrimary":"#username_field_renamed","fixedLocator":"[name=\"username\"]","backupStrategy":"ai-name","pageUrl":"https://the-internet.herokuapp.com/login"}
    ```

13. If **none** of the AI's suggestions work either, the healer tries calling the
    AI again (up to 2 retries total), and only if that also fails does it finally
    give up and fail the test for real — same as a normal test would.

## 5. Why some design choices were made

- **Only a sanitized HTML snippet is sent to the AI**, not a screenshot — this
  keeps things fast, avoids sending image data, and is enough for a text model
  to reason about tags/attributes.
- **The model runs locally (Ollama)** instead of calling an API like OpenAI —
  no API key, no per-request cost, nothing leaves your machine. The tradeoff is
  that small local models are weaker reasoners than large cloud models, so this
  repo intentionally uses `llama3.2:3b` rather than the tiny `1b` version, which
  wasn't reliable enough to produce valid locators.
- **The healed locator is never written back into a test file.** It only exists
  in memory for that one test run (`locator_strategies`), plus an audit line in
  `logs/self-heal-audit.jsonl`. Auto-editing tests would hide real product bugs
  and could persist a wrong guess. A production version might cache heals or
  open a PR for a human to review.
- **pytest-playwright defaults to headless Chromium** (`pytest.ini` pins
  `--browser chromium`). Running the browser invisibly avoids the browser and
  the AI model competing for GPU, which can make the AI call hang.

<!--
- **`headless: true`** — running the browser invisibly, not on screen — avoids
  the browser and the AI model competing for your machine's GPU at the same
  time, which was actually causing the AI call to hang during testing.
-->

## 6. The one-sentence version

*A pytest/Playwright test tries a locator, fails, hands the page's HTML and the
failed locator's details to a small AI model running locally, gets back a
corrected locator, retries against the live DOM, and logs the win — turning what
would have been a broken test into a passing one, without rewriting the test
file.*

<!--
*A test tries a locator, fails, hands the page's HTML and the failed locator's
details to a small AI model running locally, gets back a corrected locator, and
retries — turning what would have been a broken test into a passing one.*
-->
