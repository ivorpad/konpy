from typing import Final, TypeAlias

OpenAIProviderConfig: TypeAlias = dict[str, str]

OPENAI_PROVIDER_ID: Final[str] = "openai"


def createOpenAIProvider(config: OpenAIProviderConfig) -> object:
    return config

