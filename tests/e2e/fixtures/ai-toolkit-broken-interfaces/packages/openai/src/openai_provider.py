from typing import Protocol


class OpenaiProvider(BaseProvider, Protocol):
    def chat(self, model_id: str) -> object: ...


class OpenaiProviderSettings(Protocol):
    api_key: str | None
    base_url: str | None


openai: OpenaiProvider

