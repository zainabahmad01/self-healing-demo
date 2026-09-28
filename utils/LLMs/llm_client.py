import json
import os
import re

import requests

from utils.models.ai_response_model import HealedLocator
from utils.models.llm_config import LLMConfig


class LLMClient:
    def __init__(self) -> None:
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "llm-config.json")
        with open(config_path, "r", encoding="utf-8") as f:
            self.config: LLMConfig = json.load(f)
        # Only used for cloud providers; not needed for the default "local" (Ollama) provider.
        self.api_key: str = os.environ.get("OPENAI_API_KEY") or self.config.get("apiKey") or ""

    def find_alternative_locator(
        self,
        locator_type: str,
        locator_value: str,
        page_source: str,
    ) -> HealedLocator:
        prompt = f"""
You are an expert Test Automation Engineer using Playwright.
Your task is to analyze the provided HTML Page Source and find robust alternative locators for a specific element that failed.

INPUT DATA:
- Failed Locator Strategy: {locator_type}
- Failed Locator Value: {locator_value}
- Page Source: (see attached below)

INSTRUCTIONS:
1. The HTML may be a truncated fragment of the page (not the full site) due to size limits.
2. Locate the element in the fragment that corresponds to the "Failed Locator" (same purpose/intent, e.g. same label, placeholder, or nearby text — the id/name itself has changed).
3. Generate a set of robust, self-healing locators for this element.
4. Prioritize attributes in this order: ID, Name, Data-TestId, Text Content, CSS Classes.
5. If the element cannot be confidently identified, return an empty JSON object {{}}.

OUTPUT FORMAT:
Return ONLY a raw JSON object with no Markdown formatting, no code blocks, and no explanations.
The JSON must follow this exact structure:
{{
  "id": "value or null",
  "name": "value or null",
  "xpath": "robust relative xpath",
  "css": "robust css selector",
  "link_text": "visible text or null"
}}

--- PAGE SOURCE BEGINS ---
{page_source}
--- PAGE SOURCE ENDS ---
    """

        llm_response = self.get_completion(prompt)
        return self._clean_and_parse_json(llm_response)

    def _clean_and_parse_json(self, response_text: str) -> HealedLocator:
        try:
            clean_text = response_text.replace("```json", "").replace("```", "").strip()
            json_match = re.search(r"\{[\s\S]*\}", clean_text)
            return json.loads(json_match.group(0) if json_match else clean_text)
        except Exception:
            print(f"[Self-heal] Failed to parse LLM JSON response: {response_text}")
            return {"id": None, "name": None, "xpath": "", "css": "", "link_text": None}

    def get_completion(self, prompt: str) -> str:
        provider = self.config["provider"].lower()

        if provider == "local":
            return self._call_local_llm(prompt)
        if provider == "openai" or provider == "api":
            return self._call_openai_compatible_api(prompt)
        raise Exception(
            f"Provider '{self.config['provider']}' is not supported. Use \"local\" (Ollama) or \"openai\"/\"api\"."
        )

    def _call_local_llm(self, prompt: str) -> str:
        """Default path: a local Ollama server. No API key needed."""
        print(f"[Self-heal] Using local LLM: {self.config['model']} ({self.config['baseUrl']})")

        request_body = {
            "model": self.config["model"],
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": self.config["temperature"],
                "num_predict": self.config["maxTokens"],
            },
        }

        try:
            response = requests.post(
                self.config["baseUrl"],
                headers={"Content-Type": "application/json"},
                data=json.dumps(request_body),
            )

            if not response.ok:
                raise Exception(f"Ollama request failed with status {response.status_code}")

            json_response = response.json()
            return json_response.get("response") or ""
        except requests.exceptions.ConnectionError as error:
            print("\n[Self-heal] ERROR: Could not connect to Ollama.")
            print("[Self-heal] SUGGESTION: Is it running? Try `ollama serve` in another terminal.\n")
            print(f"[Self-heal] Error calling local LLM: {error}")
            raise
        except Exception as error:
            print(f"[Self-heal] Error calling local LLM: {error}")
            raise

    def _call_openai_compatible_api(self, prompt: str) -> str:
        """Optional cloud fallback: set provider to "openai"/"api" in llm-config.json and OPENAI_API_KEY in the env."""
        url = re.sub(r"/$", "", self.config["baseUrl"]) + (
            "" if "/chat/completions" in self.config["baseUrl"] else "/chat/completions"
        )
        if not self.api_key:
            raise Exception('OPENAI_API_KEY must be set in the env when using provider "openai" or "api".')
        print(f"[Self-heal] Using API LLM: {self.config['model']} ({url})")

        body = {
            "model": self.config["model"],
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.config["temperature"],
            "max_tokens": self.config["maxTokens"],
        }

        response = requests.post(
            url,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            data=json.dumps(body),
        )

        if not response.ok:
            err_text = response.text
            raise Exception(f"API request failed {response.status_code}: {err_text}")

        json_response = response.json()
        content = None
        choices = json_response.get("choices")
        if choices and len(choices) > 0:
            content = choices[0].get("message", {}).get("content")
        if content is None:
            raise Exception("API response missing choices[0].message.content")
        return content
