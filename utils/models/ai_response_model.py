from typing import Optional, TypedDict


class HealedLocator(TypedDict):
    id: Optional[str]
    name: Optional[str]
    xpath: str
    css: str
    link_text: Optional[str]
