from typing import Final

plugin_id: Final[str] = "storage"


def activate() -> None:
    print("Storage plugin activated")


def deactivate() -> None:
    print("Storage plugin deactivated")

