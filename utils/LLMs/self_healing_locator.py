from typing import Optional

from playwright.sync_api import Locator, Page

from utils.LLMs.llm_client import LLMClient
from utils.LLMs.locator_helper import LocatorHelper
from utils.LLMs.self_heal_audit_log import append_self_heal_audit


class SelfHealingLocator:
    MAX_HEAL_HTML_CHARS = 60_000

    def __init__(self, page: Page, selector: str) -> None:
        self.page = page
        self.current_selector = selector
        self.locator_strategies: dict = {}
        self.locator_strategies["primary"] = selector

    def find_element(self, retries: int = 2) -> Locator:
        element = self._try_find_with_current_strategy()
        if element:
            return element

        print(f'[Self-heal] Primary locator failed: "{self.current_selector}". Trying backups...')
        element = self._try_alternative_strategies()
        if element:
            return element

        if retries > 0:
            print(f"[Self-heal] No working backups yet. Calling LLM (attempts left: {retries}).")
            self._heal_using_ai()
            return self.find_element(retries - 1)

        raise Exception(
            f"Failed to locate element '{self.current_selector}' after all healing attempts."
        )

    def _get_html_for_healing(self) -> str:
        """Sends only a sanitized DOM snippet to the LLM: strips scripts/styles/svg noise, caps size."""
        max_chars = SelfHealingLocator.MAX_HEAL_HTML_CHARS
        result = self.page.evaluate(
            """
      ({ maxChars: cap, attrCap }) => {
        const modal = document.querySelector('[role="dialog"]');
        const root = (modal ?? document.body);
        if (!root) {
          return { html: '', source: 'empty', preTrimLen: 0, postSanitizeLen: 0 };
        }

        const source = modal ? 'modal' : 'body';
        const clone = root.cloneNode(true);
        const preTrimLen = clone.outerHTML.length;

        clone
          .querySelectorAll('script,style,noscript,link[rel="stylesheet"],meta,template,object,embed,iframe')
          .forEach((el) => el.remove());

        const allEls = [clone, ...Array.from(clone.querySelectorAll('*'))];
        for (const el of allEls) {
          for (const attr of Array.from(el.attributes)) {
            const name = attr.name.toLowerCase();
            if (name === 'style' || name.startsWith('on')) {
              el.removeAttribute(attr.name);
              continue;
            }
            if (attr.value.length > attrCap) {
              el.setAttribute(attr.name, `${attr.value.slice(0, attrCap)}...`);
            }
          }
        }

        const svgs = Array.from(clone.querySelectorAll('svg'));
        svgs.sort((a, b) => (a.contains(b) ? 1 : b.contains(a) ? -1 : 0));
        for (const svg of svgs) {
          const span = document.createElement('span');
          span.setAttribute('data-self-heal-omitted', 'svg');
          svg.replaceWith(span);
        }

        let html = clone.outerHTML;
        const postSanitizeLen = html.length;
        if (html.length > cap) {
          html = html.slice(0, cap) + `\\n<!-- self-heal: truncated ${postSanitizeLen}->${cap} chars -->`;
        }
        return { html, source, preTrimLen, postSanitizeLen };
      }
      """,
            {"maxChars": max_chars, "attrCap": 400},
        )

        if result["source"] == "empty":
            print("[Self-heal] No body for HTML snapshot; sending empty fragment.")
            return ""

        print(
            f"[Self-heal] HTML for LLM: source={result['source']}, ~{result['preTrimLen']} chars raw root -> {result['postSanitizeLen']} after sanitize -> {len(result['html'])} sent"
        )
        return result["html"]

    def _heal_using_ai(self) -> None:
        try:
            page_source = self._get_html_for_healing()
            broken_locator = self.page.locator(self.current_selector)
            details = LocatorHelper.get_locator_details(broken_locator)

            print(
                f'[Self-heal] Asking LLM for alternatives (primary failed: "{self.current_selector}", parsed {details["type"]}="{details["value"]}")'
            )

            llm_client = LLMClient()
            healed_locators = llm_client.find_alternative_locator(
                details["type"], details["value"], page_source
            )

            suggested_keys = [
                k
                for k, v in healed_locators.items()
                if v is not None and str(v).strip() != ""
            ]
            print(
                f"[Self-heal] LLM suggested fields: {', '.join(suggested_keys) if len(suggested_keys) else '(none)'}"
            )

            added_count = 0
            for key, value in healed_locators.items():
                if value:
                    success = self._try_create_locator_strategy(key, str(value))
                    if success:
                        added_count += 1

            print(
                f"[Self-heal] Done. Registered {added_count} backup locator(s); retrying primary + backups."
            )
        except Exception as e:
            print(f"[Self-heal] LLM step failed: {e}")

    def _try_create_locator_strategy(self, type_: str, value: str) -> bool:
        if not value or value.strip() == "":
            return False

        valid_selector = ""

        t = type_.lower()
        if t == "id":
            valid_selector = f"#{value.replace('#', '')}"

        elif t in ("testid", "data-testid"):
            valid_selector = f'[data-testid="{value}"]'

        elif t == "placeholder":
            valid_selector = f'[placeholder="{value}"]'

        elif t == "role":
            valid_selector = f"role={value}"

        elif t == "name":
            valid_selector = f'[name="{value}"]'

        elif t in ("class", "classname"):
            valid_selector = value if value.startswith(".") else f".{value}"

        elif t in ("text", "linktext", "link_text"):
            valid_selector = f"text={value}"

        elif t in ("xpath", "css"):
            valid_selector = value

        else:
            return False

        strategy_name = f"ai-{type_}"
        self.locator_strategies[strategy_name] = valid_selector
        preview = (
            f"{valid_selector[:100]}..." if len(valid_selector) > 100 else valid_selector
        )
        print(f'[Self-heal] Using backup "{strategy_name}" -> {preview}')
        return True

    def _try_find_with_current_strategy(self) -> Optional[Locator]:
        try:
            locator = self.page.locator(self.current_selector)
            locator.wait_for(state="attached", timeout=10000)
            return locator
        except Exception as e:
            print(f"[Self-heal] Primary wait failed: {e}")
            return None

    def _try_alternative_strategies(self) -> Optional[Locator]:
        if len(self.locator_strategies) <= 1:
            return None

        for strategy_name, selector in self.locator_strategies.items():
            if strategy_name == "primary":
                continue

            print(
                f'[Self-heal] Trying backup "{strategy_name}": {selector[:80] + "..." if len(selector) > 80 else selector}'
            )
            try:
                locator = self.page.locator(selector)
                locator.wait_for(state="attached", timeout=2000)
                print(f'[Self-heal] Backup "{strategy_name}" matched; continuing.')
                append_self_heal_audit(
                    {
                        "brokenPrimary": self.current_selector,
                        "fixedLocator": selector,
                        "backupStrategy": strategy_name,
                        "pageUrl": self.page.url,
                    }
                )
                return locator
            except Exception:
                # try next strategy
                pass
        return None
