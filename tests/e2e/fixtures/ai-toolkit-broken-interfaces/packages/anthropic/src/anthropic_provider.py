from typing import Protocol


class AnthropicProvider:
    def messages(self, model_id: str) -> object:
        return model_id


class AnthropicProviderSettings(Protocol):
    api_key: str | None
    base_url: str | None


anthropic = AnthropicProvider()

