from pathlib import Path

if TYPE_CHECKING:
    from collections.abc import Mapping


def parent(options: Mapping[str, str]) -> Path:
    return Path(options["path"])

