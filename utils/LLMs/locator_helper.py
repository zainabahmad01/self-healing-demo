from playwright.sync_api import Locator


class LocatorHelper:
    @staticmethod
    def get_locator_details(locator: Locator) -> dict:
        # Python Playwright keeps the raw selector on the internal impl object.
        impl = getattr(locator, "_impl_obj", None)
        selector = getattr(impl, "_selector", None) or getattr(
            locator, "_selector", None
        )
        if selector is None:
            selector = str(locator)

        clean_selector = (
            selector.replace("Locator@", "").replace("locator('", "").replace("')", "")
        )

        if clean_selector.startswith("id="):
            return {"type": "id", "value": clean_selector[3:]}
        if clean_selector.startswith("#"):
            return {"type": "id", "value": clean_selector[1:]}

        if clean_selector.startswith("data-testid="):
            return {"type": "testid", "value": clean_selector[12:]}

        if clean_selector.startswith("text="):
            return {"type": "text", "value": clean_selector[5:]}

        if clean_selector.startswith("placeholder="):
            return {"type": "placeholder", "value": clean_selector[12:]}

        if clean_selector.startswith("role="):
            return {"type": "role", "value": clean_selector[5:]}

        if clean_selector.startswith("."):
            return {"type": "class", "value": clean_selector[1:]}

        if clean_selector.startswith("//") or clean_selector.startswith("xpath="):
            return {"type": "xpath", "value": clean_selector}

        return {"type": "css", "value": clean_selector}
