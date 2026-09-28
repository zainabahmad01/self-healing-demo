# self-healing-demo

Minimal Playwright example of self-healing locators: when a locator breaks, the failure
is sent to a local AI model (Ollama), which suggests a replacement locator, and the test
retries with it instead of failing.

The core logic (`utils/LLMs/self_healing_locator.py` + `llm_client.py` + `locator_helper.py`)
is adapted from `ai-workers-automation`, with the local-model path kept plugged in as the
main path (not commented out) and pointed at Ollama instead of an OpenAI-compatible API.

This project uses **Playwright for Python** driven by **pytest** (`pytest-playwright`).

## How it works

1. `tests/test_self_healing_login.py` intentionally uses a wrong selector for the
   username field on https://the-internet.herokuapp.com/login (`#username_field_renamed`
   instead of the real `#username`).
2. `SelfHealingLocator.find_element()` tries that selector, fails, then sends a sanitized
   snapshot of the page HTML plus the broken locator's type/value to the local LLM.
3. The LLM (running via Ollama) responds with candidate locators (id/name/css/xpath/text).
4. Each candidate is tried until one matches; the login flow continues with the healed
   locator.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

Make sure Ollama is running with the model configured in `utils/LLMs/llm-config.json`
(defaults to `llama3.2:3b`):

```bash
ollama serve   # if not already running
ollama pull llama3.2:3b
```

## Run

```bash
pytest
```

Watch the console — it logs the broken locator, the healing attempt, what the LLM
suggested, and which backup locator ultimately worked.

## Switching to a cloud model instead

Edit `utils/LLMs/llm-config.json`: set `"provider": "openai"` (or `"api"`), point
`baseUrl`/`model` at your provider, and set `OPENAI_API_KEY` in the environment.
