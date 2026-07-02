from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from ai_toolkit.core import ProviderV1


class OpenaiProvider(Pick[ProviderV1, str], Protocol):
    def completions(self, model_id: str) -> object: ...


class OpenaiProviderSettings(Protocol):
    api_key: str | None
    base_url: str | None


openai: OpenaiProvider

