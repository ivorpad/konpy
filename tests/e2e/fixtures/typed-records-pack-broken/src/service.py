from __future__ import annotations

from typing import Any

VALUE: dict[str, str | int] = {}


class Model:
    metadata: dict[str, object]


def handle(payload: dict[str, Any]) -> dict[str, object]:
    return payload


def nested(items: list[dict[str, Any]]) -> None:
    pass
