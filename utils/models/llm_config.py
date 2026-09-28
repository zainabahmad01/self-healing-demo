from typing import TypedDict


class LLMConfig(TypedDict):
    provider: str
    apiKey: str
    baseUrl: str
    model: str
    temperature: float
    maxTokens: int
