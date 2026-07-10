from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict


class Payload(TypedDict):
    name: str
    tags: list[str]


@dataclass(frozen=True)
class Result:
    status: str
    count: int


SETTINGS: dict[str, str] = {}


class Model:
    metadata: dict[str, str]


def handle(payload: Payload) -> Result:
    return Result(status=payload["name"], count=len(payload["tags"]))


def by_name(values: dict[str, int]) -> dict[str, str]:
    return {key: str(value) for key, value in values.items()}
