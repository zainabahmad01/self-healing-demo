import pytest
from playwright.sync_api import Page, expect

from utils.LLMs.self_healing_locator import SelfHealingLocator


# Self-healing calls a local LLM (Ollama) when a locator breaks, so give it room to think.
@pytest.mark.timeout(120)
def test_self_heals_a_broken_locator_on_the_login_form(page: Page):
    page.goto("https://the-internet.herokuapp.com/login")

    # This id is deliberately wrong. The real field is #username.
    broken_username_selector = "#username_field_renamed"

    print(f'\n[Test] Broken locator on purpose: "{broken_username_selector}"')
    username_field = SelfHealingLocator(page, broken_username_selector).find_element()
    print("[Test] Self-healing recovered a working locator, proceeding with the login flow.\n")

    username_field.fill("tomsmith")
    page.locator("#password").fill("SuperSecretPassword!")
    page.locator('button[type="submit"]').click()

    expect(page.locator(".flash.success")).to_be_visible()
