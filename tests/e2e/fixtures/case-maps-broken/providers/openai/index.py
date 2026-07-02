from typing import TypeAlias

OpenaiProviderConfig: TypeAlias = dict[str, str]


def createOpenaiProvider(config: OpenaiProviderConfig) -> object:
    return config

