from typing import Final, Protocol

OPENAI_ID: Final[str] = "openai"


class OpenaiProvider(Protocol):
    id: str


openai: OpenaiProvider

