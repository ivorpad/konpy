from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from ai_toolkit.core import ProviderV1


class AnthropicProvider(ProviderV1, Protocol):
    def messages(self, model_id: str) -> object: ...


class AnthropicProviderSettings(Protocol):
    api_key: str | None
    base_url: str | None


anthropic: AnthropicProvider

