from typing import Protocol


class ThingConfig(Protocol):
    name: str


def createThing(config: ThingConfig) -> dict[str, str]:
    return {"name": config.name}

