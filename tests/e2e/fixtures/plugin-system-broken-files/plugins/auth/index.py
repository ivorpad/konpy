from typing import Final

plugin_id: Final[str] = "auth"


def activate() -> None:
    print("Auth plugin activated")


def deactivate() -> None:
    print("Auth plugin deactivated")

