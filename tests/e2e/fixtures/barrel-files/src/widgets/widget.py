from typing import Final

WIDGET_KIND: Final[str] = "widget"


def makeWidget(name: str) -> dict[str, str]:
    return {"name": name}

