from typing import Final

__all__ = ["activate"]

plugin_id: Final[str] = "storage"


def activate() -> None:
    print("Storage plugin activated")

