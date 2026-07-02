from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from ai_toolkit.core import ProviderV1


class OpenaiProvider(ProviderV1, Protocol):
    def chat(self, model_id: str) -> object: ...


class OpenaiProviderSettings(Protocol):
    api_key: str | None
    base_url: str | None


openai: OpenaiProvider

